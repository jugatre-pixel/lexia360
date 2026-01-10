import os
import json
import traceback
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlmodel import SQLModel, Field, Session, select, create_engine


# ============================================================
# CONFIG
# ============================================================
APP_VERSION = "lexia360-v5-detached-fix"

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("❌ Falta DATABASE_URL")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("❌ Falta SECRET_KEY")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# DB engine
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

# Password hashing (NO bcrypt)
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# OAuth2
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# ============================================================
# APP
# ============================================================
app = FastAPI(title="Lexia360")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Log server-side errors to Render logs
@app.middleware("http")
async def catch_exceptions(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        traceback.print_exc()
        raise

# Static
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static", html=True), name="static")


# ============================================================
# DB MODELS
# ============================================================
class Usuario(SQLModel, table=True):
    id_usuario: int | None = Field(default=None, primary_key=True)
    nombre: str
    email: str = Field(index=True)
    hashed_password: str
    rol: str = "cliente"


class Inmueble(SQLModel, table=True):
    id_inmueble: int | None = Field(default=None, primary_key=True)
    id_usuario: int = Field(index=True, foreign_key="usuario.id_usuario")

    direccion: str
    municipio: str
    comunidad_autonoma: str
    codigo_postal: str | None = None
    superficie_m2: int | None = None

    tipo_arrendamiento: str = "vivienda_habitual"  # MVP
    tipo_arrendador: str = "persona_fisica"        # persona_fisica / persona_juridica

    renta_propuesta: float
    renta_anterior: float | None = None

    creado_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RuleRun(SQLModel, table=True):
    id_run: int | None = Field(default=None, primary_key=True)
    id_inmueble: int = Field(index=True, foreign_key="inmueble.id_inmueble")

    version: str = APP_VERSION
    creado_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    resultados_json: str
    alertas_json: str


# ============================================================
# SCHEMAS
# ============================================================
class RegisterPayload(BaseModel):
    nombre: str
    email: EmailStr
    password: str


class InmuebleCreate(BaseModel):
    direccion: str
    municipio: str
    comunidad_autonoma: str
    codigo_postal: str | None = None
    superficie_m2: int | None = None
    tipo_arrendamiento: str = "vivienda_habitual"
    tipo_arrendador: str = "persona_fisica"
    renta_propuesta: float
    renta_anterior: float | None = None


# ============================================================
# STARTUP
# ============================================================
@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)
    print("✅ STARTUP OK ->", APP_VERSION)


# ============================================================
# HELPERS (AUTH)
# ============================================================
def validate_password(password: str):
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)) -> Usuario:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

    # ✅ expire_on_commit=False evita objetos "detached" tras commits
    with Session(engine, expire_on_commit=False) as session:
        user = session.exec(select(Usuario).where(Usuario.email == email)).first()
        if not user:
            raise HTTPException(status_code=401, detail="Usuario no existe")
        return user


# ============================================================
# RULE ENGINE (MVP)
# ============================================================
ZONAS_TENSIONADAS_MVP = {"Madrid", "Barcelona", "Valencia"}  # placeholder

def evaluar_reglas(inmueble: Inmueble) -> tuple[dict, list[str]]:
    resultados: dict = {}
    alertas: list[str] = []

    # 1) Duración mínima (simplificada)
    duracion = 5 if inmueble.tipo_arrendador == "persona_fisica" else 7
    resultados["duracion_minima_anios"] = duracion
    alertas.append(f"Duración mínima aplicable: {duracion} años.")

    # 2) Zona tensionada (MVP por municipio)
    zona_tensionada = inmueble.municipio.strip() in ZONAS_TENSIONADAS_MVP
    resultados["zona_tensionada"] = zona_tensionada
    if zona_tensionada:
        alertas.append("El inmueble está en zona tensionada (MVP). Se aplican limitaciones específicas.")
    else:
        alertas.append("El inmueble NO está en zona tensionada (MVP).")

    # 3) Renta (MVP)
    if zona_tensionada:
        renta_max = inmueble.renta_anterior if inmueble.renta_anterior is not None else inmueble.renta_propuesta
        resultados["renta_maxima_mvp"] = renta_max
        if inmueble.renta_propuesta > renta_max:
            alertas.append(f"⚠️ Renta propuesta ({inmueble.renta_propuesta}€) supera renta máxima (MVP) ({renta_max}€).")
        else:
            alertas.append("Renta propuesta dentro del límite (MVP).")
    else:
        resultados["renta_maxima_mvp"] = None
        alertas.append("Renta inicial libre (régimen general, MVP).")

    # 4) Fianza (vivienda habitual = 1 mes)
    resultados["fianza_minima"] = inmueble.renta_propuesta
    alertas.append(f"Fianza mínima: {inmueble.renta_propuesta}€ (1 mensualidad).")

    # Semáforo simple
    if zona_tensionada and resultados["renta_maxima_mvp"] is not None and inmueble.renta_propuesta > resultados["renta_maxima_mvp"]:
        resultados["semaforo"] = "ROJO"
    else:
        resultados["semaforo"] = "VERDE"

    return resultados, alertas


# ============================================================
# ROUTES (PUBLIC)
# ============================================================
@app.get("/version")
def version():
    return {"version": APP_VERSION}

@app.get("/")
def root():
    return {"mensaje": "Lexia360 API OK 🚀", "static": "/static/index.html", "version": APP_VERSION}

@app.head("/")
def head_root():
    return Response(status_code=200)

@app.get("/status")
def status():
    with Session(engine, expire_on_commit=False) as session:
        users_count = len(session.exec(select(Usuario)).all())
        return {"status": "✅ OK", "usuarios_registrados": users_count, "version": APP_VERSION}


# ============================================================
# ROUTES (AUTH)
# ============================================================
@app.post("/register")
def register(payload: RegisterPayload):
    validate_password(payload.password)

    with Session(engine, expire_on_commit=False) as session:
        existing = session.exec(select(Usuario).where(Usuario.email == payload.email)).first()
        if existing:
            raise HTTPException(status_code=400, detail="El usuario ya existe")

        user = Usuario(
            nombre=payload.nombre,
            email=payload.email,
            hashed_password=get_password_hash(payload.password),
        )
        session.add(user)
        session.commit()

    return {"mensaje": "✅ Registro completado", "version": APP_VERSION}

@app.post("/token")
def login(form: OAuth2PasswordRequestForm = Depends()):
    with Session(engine, expire_on_commit=False) as session:
        user = session.exec(select(Usuario).where(Usuario.email == form.username)).first()
        if not user or not verify_password(form.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    token = create_access_token(user.email)
    return {"access_token": token, "token_type": "bearer", "version": APP_VERSION}

@app.get("/me")
def me(user: Usuario = Depends(get_current_user)):
    return {"id_usuario": user.id_usuario, "email": user.email, "rol": user.rol, "version": APP_VERSION}


# ============================================================
# ROUTES (INMUEBLES) - PROTECTED
# ============================================================
@app.post("/inmuebles")
def crear_inmueble(payload: InmuebleCreate, user: Usuario = Depends(get_current_user)):
    # ✅ expire_on_commit=False + response dentro => NO detached error
    with Session(engine, expire_on_commit=False) as session:
        inm = Inmueble(
            id_usuario=user.id_usuario,
            direccion=payload.direccion,
            municipio=payload.municipio,
            comunidad_autonoma=payload.comunidad_autonoma,
            codigo_postal=payload.codigo_postal,
            superficie_m2=payload.superficie_m2,
            tipo_arrendamiento=payload.tipo_arrendamiento,
            tipo_arrendador=payload.tipo_arrendador,
            renta_propuesta=payload.renta_propuesta,
            renta_anterior=payload.renta_anterior,
        )
        session.add(inm)
        session.commit()
        session.refresh(inm)

        resultados, alertas = evaluar_reglas(inm)

        run = RuleRun(
            id_inmueble=inm.id_inmueble,
            resultados_json=json.dumps(resultados, ensure_ascii=False),
            alertas_json=json.dumps(alertas, ensure_ascii=False),
        )
        session.add(run)
        session.commit()

        out = {
            "mensaje": "✅ Inmueble creado y reglas ejecutadas",
            "inmueble": {
                "id_inmueble": inm.id_inmueble,
                "direccion": inm.direccion,
                "municipio": inm.municipio,
                "comunidad_autonoma": inm.comunidad_autonoma,
                "renta_propuesta": inm.renta_propuesta,
            },
            "resultados": resultados,
            "alertas": alertas,
            "version": APP_VERSION,
        }

    return out

@app.get("/inmuebles")
def listar_inmuebles(user: Usuario = Depends(get_current_user)):
    with Session(engine, expire_on_commit=False) as session:
        inmuebles = session.exec(
            select(Inmueble).where(Inmueble.id_usuario == user.id_usuario)
        ).all()

        out = []
        for inm in inmuebles:
            last_run = session.exec(
                select(RuleRun)
                .where(RuleRun.id_inmueble == inm.id_inmueble)
                .order_by(RuleRun.id_run.desc())
            ).first()

            resultados = json.loads(last_run.resultados_json) if last_run else None
            alertas = json.loads(last_run.alertas_json) if last_run else None

            out.append({
                "id_inmueble": inm.id_inmueble,
                "direccion": inm.direccion,
                "municipio": inm.municipio,
                "comunidad_autonoma": inm.comunidad_autonoma,
                "renta_propuesta": inm.renta_propuesta,
                "semaforo": resultados.get("semaforo") if resultados else None,
                "resultados": resultados,
                "alertas": alertas,
            })

    return out

