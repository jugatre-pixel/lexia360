import os
import json
import traceback
import secrets
from datetime import datetime, timedelta, timezone, date

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
APP_VERSION = "lexia360-v8-inmueble-id-fixed"

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("❌ Falta DATABASE_URL (Render -> Environment Variables)")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("❌ Falta SECRET_KEY (Render -> Environment Variables)")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

# Hash sin límite 72 bytes (NO bcrypt)
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def load_secret_from_env_or_file(env_name: str, file_path: str) -> str:
    val = os.getenv(env_name, "").strip()
    if val:
        return val
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


# Render Free: Secret Files
ADMIN_BOOTSTRAP_SECRET = load_secret_from_env_or_file(
    "ADMIN_BOOTSTRAP_SECRET",
    "/etc/secrets/ADMIN_BOOTSTRAP_SECRET"
)


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

@app.middleware("http")
async def catch_exceptions(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        traceback.print_exc()
        raise

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
    rol: str = "cliente"  # cliente | admin


class Inmueble(SQLModel, table=True):
    id_inmueble: int | None = Field(default=None, primary_key=True)
    id_usuario: int = Field(index=True, foreign_key="usuario.id_usuario")

    direccion: str
    municipio: str
    comunidad_autonoma: str
    codigo_postal: str | None = None
    superficie_m2: int | None = None

    tipo_arrendamiento: str = "vivienda_habitual"
    tipo_arrendador: str = "persona_fisica"  # persona_fisica / persona_juridica

    renta_propuesta: float
    renta_anterior: float | None = None

    creado_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RuleRun(SQLModel, table=True):
    id_run: int | None = Field(default=None, primary_key=True)
    id_inmueble: int = Field(index=True, foreign_key="inmueble.id_inmueble")

    version: str = APP_VERSION
    creado_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    fecha_analisis: date

    resultados_json: str
    alertas_json: str


class ZonaTensionada(SQLModel, table=True):
    id_zona: int | None = Field(default=None, primary_key=True)

    comunidad_autonoma: str = Field(index=True)
    municipio: str = Field(index=True)

    fecha_inicio: date
    fecha_fin: date | None = None

    fuente_oficial: str
    activo: bool = True

    creado_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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


class ZonaCreate(BaseModel):
    comunidad_autonoma: str
    municipio: str
    fecha_inicio: date
    fecha_fin: date | None = None
    fuente_oficial: str
    activo: bool = True


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

    with Session(engine, expire_on_commit=False) as session:
        user = session.exec(select(Usuario).where(Usuario.email == email)).first()
        if not user:
            raise HTTPException(status_code=401, detail="Usuario no existe")
        return user

def require_admin(user: Usuario = Depends(get_current_user)) -> Usuario:
    if user.rol != "admin":
        raise HTTPException(status_code=403, detail="No autorizado (admin)")
    return user


# ============================================================
# ZONAS TENSIONADAS
# ============================================================
def find_zona_tensionada(session: Session, municipio: str, comunidad_autonoma: str, fecha: date) -> ZonaTensionada | None:
    mun = municipio.strip()
    ca = comunidad_autonoma.strip()

    return session.exec(
        select(ZonaTensionada)
        .where(ZonaTensionada.municipio == mun)
        .where(ZonaTensionada.comunidad_autonoma == ca)
        .where(ZonaTensionada.fecha_inicio <= fecha)
        .where((ZonaTensionada.fecha_fin == None) | (ZonaTensionada.fecha_fin >= fecha))
        .where(ZonaTensionada.activo == True)
        .order_by(ZonaTensionada.fecha_inicio.desc())
    ).first()


# ============================================================
# RULE ENGINE (MVP)
# ============================================================
def evaluar_reglas(session: Session, inmueble: Inmueble, fecha_analisis: date) -> tuple[dict, list[str]]:
    resultados: dict = {}
    alertas: list[str] = []

    duracion = 5 if inmueble.tipo_arrendador == "persona_fisica" else 7
    resultados["duracion_minima_anios"] = duracion
    alertas.append(f"Duración mínima aplicable: {duracion} años.")

    zona = find_zona_tensionada(session, inmueble.municipio, inmueble.comunidad_autonoma, fecha_analisis)
    zona_tensionada = zona is not None
    resultados["zona_tensionada"] = zona_tensionada
    resultados["zona_tensionada_fuente"] = zona.fuente_oficial if zona else None
    resultados["fecha_analisis"] = str(fecha_analisis)

    if zona_tensionada:
        alertas.append("El inmueble está en zona tensionada (según dataset cargado).")
        if zona and zona.fuente_oficial:
            alertas.append(f"Fuente oficial: {zona.fuente_oficial}")
    else:
        alertas.append("El inmueble NO está en zona tensionada (según dataset cargado).")

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

    resultados["fianza_minima"] = inmueble.renta_propuesta
    alertas.append(f"Fianza mínima: {inmueble.renta_propuesta}€ (1 mensualidad).")

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
        zonas_count = len(session.exec(select(ZonaTensionada)).all())
        return {
            "status": "✅ OK",
            "usuarios_registrados": users_count,
            "zonas_tensionadas": zonas_count,
            "version": APP_VERSION
        }

@app.get("/debug/env")
def debug_env():
    val_env = os.getenv("ADMIN_BOOTSTRAP_SECRET", "").strip()

    val_file = ""
    p = "/etc/secrets/ADMIN_BOOTSTRAP_SECRET"
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                val_file = f.read().strip()
        except Exception:
            val_file = ""

    return {
        "env_has_admin_secret": bool(val_env),
        "env_len": len(val_env),
        "file_has_admin_secret": bool(val_file),
        "file_len": len(val_file),
        "effective_has_admin_secret": bool(ADMIN_BOOTSTRAP_SECRET),
        "effective_len": len(ADMIN_BOOTSTRAP_SECRET),
    }


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
            rol="cliente"
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
# TEMP ADMIN BOOTSTRAP
# ============================================================
@app.post("/admin/bootstrap")
def bootstrap_admin(secret: str, user: Usuario = Depends(get_current_user)):
    if not ADMIN_BOOTSTRAP_SECRET:
        raise HTTPException(status_code=500, detail="ADMIN_BOOTSTRAP_SECRET vacío (Secret File no montado).")
    if not secrets.compare_digest(secret, ADMIN_BOOTSTRAP_SECRET):
        raise HTTPException(status_code=403, detail="Secreto incorrecto")

    with Session(engine, expire_on_commit=False) as session:
        db_user = session.exec(select(Usuario).where(Usuario.email == user.email)).first()
        if not db_user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado en BD")
        db_user.rol = "admin"
        session.add(db_user)
        session.commit()

    return {"ok": True, "mensaje": f"✅ {user.email} ahora es admin"}


# ============================================================
# ROUTES (ZONAS TENSIONADAS)
# ============================================================
@app.get("/zonas-tensionadas/check")
def check_zona(municipio: str, comunidad_autonoma: str, fecha: date | None = None):
    f = fecha or date.today()
    with Session(engine, expire_on_commit=False) as session:
        zona = find_zona_tensionada(session, municipio, comunidad_autonoma, f)
        return {
            "municipio": municipio,
            "comunidad_autonoma": comunidad_autonoma,
            "fecha": str(f),
            "zona_tensionada": zona is not None,
            "fuente_oficial": zona.fuente_oficial if zona else None
        }

@app.post("/admin/zonas-tensionadas")
def crear_zona(payload: ZonaCreate, admin: Usuario = Depends(require_admin)):
    with Session(engine, expire_on_commit=False) as session:
        z = ZonaTensionada(
            comunidad_autonoma=payload.comunidad_autonoma.strip(),
            municipio=payload.municipio.strip(),
            fecha_inicio=payload.fecha_inicio,
            fecha_fin=payload.fecha_fin,
            fuente_oficial=payload.fuente_oficial.strip(),
            activo=payload.activo
        )
        session.add(z)
        session.commit()
        session.refresh(z)
        return {
            "ok": True,
            "id_zona": z.id_zona,
            "comunidad_autonoma": z.comunidad_autonoma,
            "municipio": z.municipio,
            "fecha_inicio": str(z.fecha_inicio),
            "fecha_fin": str(z.fecha_fin) if z.fecha_fin else None,
            "fuente_oficial": z.fuente_oficial,
            "activo": z.activo
        }

@app.get("/admin/zonas-tensionadas")
def listar_zonas(admin: Usuario = Depends(require_admin)):
    with Session(engine, expire_on_commit=False) as session:
        zonas = session.exec(
            select(ZonaTensionada).order_by(ZonaTensionada.comunidad_autonoma, ZonaTensionada.municipio)
        ).all()
        return [{
            "id_zona": z.id_zona,
            "comunidad_autonoma": z.comunidad_autonoma,
            "municipio": z.municipio,
            "fecha_inicio": str(z.fecha_inicio),
            "fecha_fin": str(z.fecha_fin) if z.fecha_fin else None,
            "fuente_oficial": z.fuente_oficial,
            "activo": z.activo,
        } for z in zonas]


# ============================================================
# ROUTES (INMUEBLES)
# ============================================================
@app.post("/inmuebles")
def crear_inmueble(payload: InmuebleCreate, user: Usuario = Depends(get_current_user)):
    fecha_analisis = date.today()
    with Session(engine, expire_on_commit=False) as session:
        inm = Inmueble(
            id_usuario=user.id_usuario,
            direccion=payload.direccion.strip(),
            municipio=payload.municipio.strip(),
            comunidad_autonoma=payload.comunidad_autonoma.strip(),
            codigo_postal=(payload.codigo_postal.strip() if payload.codigo_postal else None),
            superficie_m2=payload.superficie_m2,
            tipo_arrendamiento=payload.tipo_arrendamiento,
            tipo_arrendador=payload.tipo_arrendador,
            renta_propuesta=payload.renta_propuesta,
            renta_anterior=payload.renta_anterior,
        )
        session.add(inm)
        session.commit()
        session.refresh(inm)

        resultados, alertas = evaluar_reglas(session, inm, fecha_analisis)

        run = RuleRun(
            id_inmueble=inm.id_inmueble,
            fecha_analisis=fecha_analisis,
            resultados_json=json.dumps(resultados, ensure_ascii=False),
            alertas_json=json.dumps(alertas, ensure_ascii=False),
        )
        session.add(run)
        session.commit()

        return {
            "mensaje": "✅ Inmueble creado y reglas ejecutadas",
            "fecha_analisis": str(fecha_analisis),
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

def inmueble_to_out(session: Session, inm: Inmueble) -> dict:
    last_run = session.exec(
        select(RuleRun)
        .where(RuleRun.id_inmueble == inm.id_inmueble)
        .order_by(RuleRun.id_run.desc())
    ).first()

    resultados = json.loads(last_run.resultados_json) if last_run else {}
    alertas = json.loads(last_run.alertas_json) if last_run else []

    return {
        "id_inmueble": inm.id_inmueble,
        "direccion": inm.direccion,
        "municipio": inm.municipio,
        "comunidad_autonoma": inm.comunidad_autonoma,
        "renta_propuesta": inm.renta_propuesta,
        "semaforo": resultados.get("semaforo"),
        "fecha_analisis": str(last_run.fecha_analisis) if last_run else None,
        "zona_tensionada": resultados.get("zona_tensionada"),
        "zona_tensionada_fuente": resultados.get("zona_tensionada_fuente"),
        "resultados": resultados,
        "alertas": alertas,
    }

@app.get("/inmuebles")
def listar_inmuebles(user: Usuario = Depends(get_current_user)):
    try:
        with Session(engine, expire_on_commit=False) as session:
            inmuebles = session.exec(
                select(Inmueble)
                .where(Inmueble.id_usuario == user.id_usuario)
                .order_by(Inmueble.id_inmueble.desc())
            ).all()
            return [inmueble_to_out(session, inm) for inm in inmuebles]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB_ERROR: {type(e).__name__}: {str(e)}")

@app.get("/inmuebles/{id_inmueble}")
def get_inmueble(id_inmueble: int, user: Usuario = Depends(get_current_user)):
    """
    ✅ Devuelve SOLO un inmueble (del usuario logueado) con su último RuleRun.
    """
    try:
        with Session(engine, expire_on_commit=False) as session:
            inm = session.exec(
                select(Inmueble)
                .where(Inmueble.id_inmueble == id_inmueble)
                .where(Inmueble.id_usuario == user.id_usuario)
            ).first()

            if not inm:
                raise HTTPException(status_code=404, detail="Inmueble no encontrado")

            return inmueble_to_out(session, inm)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB_ERROR: {type(e).__name__}: {str(e)}")
