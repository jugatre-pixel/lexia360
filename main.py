import os
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


# ------------------------------------------------------------
# 🌐 APP
# ------------------------------------------------------------
app = FastAPI(title="Lexia360")

# Middleware para ver los 500 en logs (Render)
@app.middleware("http")
async def catch_exceptions(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        traceback.print_exc()
        raise


# ------------------------------------------------------------
# 🌍 CORS
# ------------------------------------------------------------
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if ALLOWED_ORIGINS == ["*"] else ALLOWED_ORIGINS,
    allow_credentials=False if ALLOWED_ORIGINS == ["*"] else True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------
# 📁 STATIC
# ------------------------------------------------------------
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static", html=True), name="static")

# ------------------------------------------------------------
# 🧱 DB (Render compatible)
# ------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("❌ Falta DATABASE_URL en variables de entorno")

# Render a veces usa postgres:// y SQLAlchemy prefiere postgresql+psycopg2://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

# ------------------------------------------------------------
# 🔐 JWT
# ------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("❌ Falta SECRET_KEY en variables de entorno")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# ------------------------------------------------------------
# 📦 DB MODELS
# ------------------------------------------------------------
class Usuario(SQLModel, table=True):
    id_usuario: int | None = Field(default=None, primary_key=True)
    nombre: str
    email: str = Field(index=True)
    hashed_password: str
    rol: str = "cliente"


# ------------------------------------------------------------
# 📦 SCHEMAS
# ------------------------------------------------------------
class RegisterPayload(BaseModel):
    nombre: str
    email: EmailStr
    password: str


# ------------------------------------------------------------
# ⚙️ STARTUP
# ------------------------------------------------------------
@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)


# ------------------------------------------------------------
# 🔧 HELPERS
# ------------------------------------------------------------
def validate_password(password: str):
    # mínimo
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres")

    # bcrypt: máximo 72 bytes (ojo emojis)
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=400,
            detail="La contraseña es demasiado larga (máx. 72 bytes). Usa una contraseña más corta."
        )

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(subject_email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject_email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)) -> Usuario:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

    with Session(engine) as session:
        user = session.exec(select(Usuario).where(Usuario.email == email)).first()
        if not user:
            raise HTTPException(status_code=401, detail="Usuario no existe")
        return user


# ------------------------------------------------------------
# ✅ ROUTES
# ------------------------------------------------------------
@app.get("/")
def root():
    return {"mensaje": "Lexia360 API OK 🚀", "static": "/static/index.html"}

# Render hace a veces HEAD /
@app.head("/")
def head_root():
    return Response(status_code=200)

@app.get("/status")
def status():
    with Session(engine) as session:
        users = session.exec(select(Usuario)).all()
        return {
            "status": "✅ OK",
            "mensaje": "Servidor funcionando",
            "usuarios_registrados": len(users),
        }

@app.post("/register")
def register_user(payload: RegisterPayload):
    validate_password(payload.password)

    with Session(engine) as session:
        existing = session.exec(select(Usuario).where(Usuario.email == str(payload.email))).first()
        if existing:
            raise HTTPException(status_code=400, detail="El usuario ya existe")

        user = Usuario(
            nombre=payload.nombre,
            email=str(payload.email),
            hashed_password=get_password_hash(payload.password),
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    return {"mensaje": "✅ Registro completado. Ya puedes iniciar sesión."}

@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    with Session(engine) as session:
        user = session.exec(select(Usuario).where(Usuario.email == form_data.username)).first()
        if not user or not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    token = create_access_token(user.email)
    return {"access_token": token, "token_type": "bearer"}

@app.get("/me")
def me(current_user: Usuario = Depends(get_current_user)):
    return {
        "id_usuario": current_user.id_usuario,
        "nombre": current_user.nombre,
        "email": current_user.email,
        "rol": current_user.rol,
    }
