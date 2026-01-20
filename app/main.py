import os
import json
import traceback
import secrets
import io
from datetime import datetime, timedelta, date

from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlmodel import SQLModel, Field, Session, select, create_engine
from sqlalchemy import text

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm


# ============================================================
# CONFIG
# ============================================================
APP_VERSION = os.getenv("APP_VERSION", "lexia360-v16-lease-docs")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("❌ Falta DATABASE_URL (Render -> Environment Variables)")

# Render/Providers sometimes use postgres://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY:
    raise RuntimeError("❌ Falta SECRET_KEY (Render -> Environment Variables)")
if len(SECRET_KEY) < 32:
    raise RuntimeError("❌ SECRET_KEY demasiado corto (mínimo 32 caracteres)")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").strip()
ALLOW_ORIGINS = ["*"] if CORS_ORIGINS == "*" else [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

# Hash robusto (evita límites de bcrypt)
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


ADMIN_BOOTSTRAP_SECRET = load_secret_from_env_or_file(
    "ADMIN_BOOTSTRAP_SECRET",
    "/etc/secrets/ADMIN_BOOTSTRAP_SECRET"
)


# ============================================================
# APP
# ============================================================
app = FastAPI(title="Lexia360", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
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


# Static mount
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
    rol: str = Field(default="cliente")  # cliente | admin
    creado_en: datetime = Field(default_factory=datetime.utcnow)


class Inmueble(SQLModel, table=True):
    id_inmueble: int | None = Field(default=None, primary_key=True)
    id_usuario: int = Field(index=True, foreign_key="usuario.id_usuario")

    direccion: str
    municipio: str
    comunidad_autonoma: str
    codigo_postal: str | None = None
    superficie_m2: int | None = None

    tipo_arrendamiento: str = "vivienda_habitual"
    tipo_arrendador: str = "persona_fisica"

    renta_propuesta: float
    renta_anterior: float | None = None

    creado_en: datetime = Field(default_factory=datetime.utcnow)

    # soft delete
    activo: bool = Field(default=True, index=True)


class RuleRun(SQLModel, table=True):
    id_run: int | None = Field(default=None, primary_key=True)
    id_inmueble: int = Field(index=True, foreign_key="inmueble.id_inmueble")

    version: str = APP_VERSION
    creado_en: datetime = Field(default_factory=datetime.utcnow)

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

    creado_en: datetime = Field(default_factory=datetime.utcnow)


class Document(SQLModel, table=True):
    id_document: int | None = Field(default=None, primary_key=True)
    id_usuario: int = Field(index=True, foreign_key="usuario.id_usuario")
    id_inmueble: int | None = Field(default=None, index=True, foreign_key="inmueble.id_inmueble")

    tipo: str = Field(index=True)  # "lease"
    titulo: str
    payload_json: str
    pdf_bytes: bytes | None = None
    creado_en: datetime = Field(default_factory=datetime.utcnow)


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


class ChatRequest(BaseModel):
    inmueble_id: int
    mensaje: str


class ChatResponse(BaseModel):
    respuesta: str
    requiere_pro: bool = False


class LeaseDocumentCreate(BaseModel):
    inmueble_id: int

    arrendador_nombre: str
    arrendador_dni: str
    arrendatario_nombre: str
    arrendatario_dni: str

    fecha_inicio: date
    duracion_meses: int = 12
    renta_mensual: float
    fianza: float

    cuenta_pago: str | None = None
    observaciones: str | None = None


# ============================================================
# STARTUP + AUTO FIX SCHEMA
# ============================================================
def _autofix_schema():
    """
    No sustituye Alembic, pero evita roturas en MVP.
    """
    with engine.begin() as conn:
        # usuario.creado_en
        exists_user_creado = conn.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name='usuario' AND column_name='creado_en'
        """)).first()
        if not exists_user_creado:
            conn.execute(text("ALTER TABLE usuario ADD COLUMN creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            conn.execute(text("UPDATE usuario SET creado_en = CURRENT_TIMESTAMP WHERE creado_en IS NULL"))
            conn.execute(text("ALTER TABLE usuario ALTER COLUMN creado_en SET NOT NULL"))

        # usuario.rol
        exists_user_rol = conn.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name='usuario' AND column_name='rol'
        """)).first()
        if not exists_user_rol:
            conn.execute(text("ALTER TABLE usuario ADD COLUMN rol VARCHAR(32) DEFAULT 'cliente'"))
            conn.execute(text("UPDATE usuario SET rol = 'cliente' WHERE rol IS NULL"))
            conn.execute(text("ALTER TABLE usuario ALTER COLUMN rol SET NOT NULL"))

        # rulerun.fecha_analisis
        exists_fecha = conn.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name='rulerun' AND column_name='fecha_analisis'
        """)).first()
        if not exists_fecha:
            conn.execute(text("ALTER TABLE rulerun ADD COLUMN fecha_analisis DATE"))
            conn.execute(text("UPDATE rulerun SET fecha_analisis = CURRENT_DATE WHERE fecha_analisis IS NULL"))
            conn.execute(text("ALTER TABLE rulerun ALTER COLUMN fecha_analisis SET NOT NULL"))

        # inmueble.activo
        exists_activo = conn.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name='inmueble' AND column_name='activo'
        """)).first()
        if not exists_activo:
            conn.execute(text("ALTER TABLE inmueble ADD COLUMN activo BOOLEAN DEFAULT TRUE"))
            conn.execute(text("UPDATE inmueble SET activo = TRUE WHERE activo IS NULL"))
            conn.execute(text("ALTER TABLE inmueble ALTER COLUMN activo SET NOT NULL"))


@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)
    try:
        _autofix_schema()
    except Exception as e:
        print("⚠️ Autofix schema falló:", e)
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
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
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


def scalar_count(val):
    # SQLAlchemy puede devolver int o Row
    if isinstance(val, int):
        return val
    try:
        return int(val[0])
    except Exception:
        try:
            return int(val)
        except Exception:
            return 0


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

    resultados["semaforo"] = "ROJO" if (zona_tensionada and resultados["renta_maxima_mvp"] is not None and inmueble.renta_propuesta > resultados["renta_maxima_mvp"]) else "VERDE"
    return resultados, alertas


# ============================================================
# CHAT MOCK
# ============================================================
def mock_chat_engine(mensaje: str) -> tuple[str, bool]:
    m = (mensaje or "").lower().strip()
    sensitive = ["mi inmueble", "esta vivienda", "puedo subir", "me recomiendas", "qué cláusula", "que cláusula", "en mi caso", "renta máxima", "renta maxima"]
    if any(k in m for k in sensitive):
        return ("Para analizar tu caso concreto necesito acceder al informe completo del inmueble. Esta funcionalidad está disponible en la versión Pro.", True)
    if "zona tensionada" in m:
        return ("Una zona tensionada es un área declarada por la administración donde se limitan los precios del alquiler para proteger el acceso a la vivienda.", False)
    if "duración" in m or "duracion" in m:
        return ("En vivienda habitual, la duración mínima del contrato suele ser de 5 años si el arrendador es persona física y 7 años si es persona jurídica.", False)
    if "fianza" in m:
        return ("En los contratos de vivienda habitual, la fianza obligatoria es de una mensualidad de renta.", False)
    return ("Puedo ayudarte con dudas generales sobre alquiler y normativa. Si necesitas un análisis específico de tu inmueble, la versión Pro te dará acceso completo.", False)


# ============================================================
# HELPERS (INMUEBLES OUT)
# ============================================================
def inmueble_to_out(session: Session, inm: Inmueble) -> dict:
    last_run = session.exec(
        select(RuleRun).where(RuleRun.id_inmueble == inm.id_inmueble).order_by(RuleRun.id_run.desc())
    ).first()

    resultados = json.loads(last_run.resultados_json) if last_run else {}
    alertas = json.loads(last_run.alertas_json) if last_run else []

    return {
        "id_inmueble": inm.id_inmueble,
        "direccion": inm.direccion,
        "municipio": inm.municipio,
        "comunidad_autonoma": inm.comunidad_autonoma,
        "codigo_postal": inm.codigo_postal,
        "superficie_m2": inm.superficie_m2,
        "tipo_arrendamiento": inm.tipo_arrendamiento,
        "tipo_arrendador": inm.tipo_arrendador,
        "renta_propuesta": inm.renta_propuesta,
        "renta_anterior": inm.renta_anterior,
        "activo": inm.activo,
        "semaforo": resultados.get("semaforo") if resultados else None,
        "fecha_analisis": str(last_run.fecha_analisis) if last_run else None,
        "zona_tensionada": resultados.get("zona_tensionada") if resultados else None,
        "zona_tensionada_fuente": resultados.get("zona_tensionada_fuente") if resultados else None,
        "resultados": resultados,
        "alertas": alertas,
    }


# ============================================================
# PDF GENERATOR (INFORME INMUEBLE)
# ============================================================
def generar_pdf_informe(inmueble: dict) -> bytes:
    def wrap(texto: str, max_chars: int = 105) -> list[str]:
        words = (texto or "").split()
        lines, cur = [], ""
        for w in words:
            if len(cur) + len(w) + 1 <= max_chars:
                cur = (cur + " " + w).strip()
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    left = 18 * mm
    right = w - 18 * mm
    top = h - 18 * mm
    y = top

    def header(page_num: int):
        nonlocal y
        c.setFont("Helvetica-Bold", 16)
        c.drawString(left, top, "Lexia360")
        c.setFont("Helvetica", 10)
        c.drawRightString(right, top, "Informe legal del inmueble")

        c.setLineWidth(1)
        c.line(left, top - 6 * mm, right, top - 6 * mm)
        y = top - 12 * mm

        c.setFont("Helvetica", 8)
        c.setFillGray(0.35)
        c.drawString(left, 12 * mm, "Confidencial · Generado por Lexia360")
        c.drawRightString(right, 12 * mm, f"Página {page_num}")
        c.setFillGray(0)

    def section_title(t: str):
        nonlocal y
        c.setFont("Helvetica-Bold", 12)
        c.drawString(left, y, t)
        y -= 6 * mm
        c.setLineWidth(0.5)
        c.setStrokeGray(0.8)
        c.line(left, y, right, y)
        c.setStrokeGray(0)
        y -= 7 * mm

    def kv(k: str, v: str):
        nonlocal y
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left, y, f"{k}:")
        c.setFont("Helvetica", 10)
        c.drawString(left + 48 * mm, y, v)
        y -= 6 * mm

    def ensure_space(min_y: float, page_num: int) -> int:
        nonlocal y
        if y < min_y:
            c.showPage()
            page_num += 1
            header(page_num)
        return page_num

    page = 1
    header(page)

    c.setFont("Helvetica-Bold", 14)
    c.drawString(left, y, "Resumen ejecutivo")
    y -= 8 * mm

    res = inmueble.get("resultados") or {}
    sem = res.get("semaforo") or inmueble.get("semaforo") or "—"
    zona = "Sí" if res.get("zona_tensionada") else "No"
    fuente = res.get("zona_tensionada_fuente") or "—"
    fecha_analisis = res.get("fecha_analisis") or inmueble.get("fecha_analisis") or "—"
    dur = res.get("duracion_minima_anios", "—")
    renta_max = res.get("renta_maxima_mvp", None)
    fianza = res.get("fianza_minima", None)

    c.setFont("Helvetica", 10)
    resumen = [
        f"Semáforo: {sem}",
        f"Zona tensionada: {zona}",
        f"Fecha de análisis: {fecha_analisis}",
        f"Duración mínima aplicable: {dur} años",
    ]
    for line in resumen:
        c.drawString(left, y, line)
        y -= 5.5 * mm

    y -= 2 * mm
    c.setLineWidth(0.5)
    c.setStrokeGray(0.85)
    c.line(left, y, right, y)
    c.setStrokeGray(0)
    y -= 9 * mm

    section_title("1) Datos del inmueble")
    page = ensure_space(40 * mm, page)

    kv("Dirección", inmueble.get("direccion") or "—")
    kv("Municipio", inmueble.get("municipio") or "—")
    kv("Comunidad", inmueble.get("comunidad_autonoma") or "—")
    kv("Código postal", inmueble.get("codigo_postal") or "—")
    kv("Superficie", f"{inmueble.get('superficie_m2') or '—'} m²")
    kv("Tipo arrendamiento", inmueble.get("tipo_arrendamiento") or "—")
    kv("Tipo arrendador", inmueble.get("tipo_arrendador") or "—")
    kv("Renta propuesta", f"{inmueble.get('renta_propuesta') if inmueble.get('renta_propuesta') is not None else '—'} €")
    kv("Renta anterior", f"{inmueble.get('renta_anterior')} €" if inmueble.get("renta_anterior") is not None else "—")

    y -= 2 * mm
    section_title("2) Resultado automático (MVP)")
    page = ensure_space(45 * mm, page)

    kv("Semáforo de riesgo", sem)
    kv("Zona tensionada", zona)
    kv("Fuente oficial", fuente)
    kv("Duración mínima", f"{dur} años")
    kv("Renta máxima (MVP)", f"{renta_max} €" if renta_max is not None else "—")
    kv("Fianza mínima (MVP)", f"{fianza} €" if fianza is not None else "—")

    y -= 2 * mm
    section_title("3) Alertas y recomendaciones")
    page = ensure_space(45 * mm, page)

    alertas = inmueble.get("alertas") or []
    if not alertas:
        alertas = ["—"]

    c.setFont("Helvetica", 10)
    def wrap2(texto: str, max_chars: int = 110) -> list[str]:
        words = (texto or "").split()
        lines, cur = [], ""
        for w in words:
            if len(cur) + len(w) + 1 <= max_chars:
                cur = (cur + " " + w).strip()
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    for a in alertas:
        page = ensure_space(28 * mm, page)
        for line in wrap2(f"• {a}", max_chars=110):
            c.drawString(left, y, line)
            y -= 5.2 * mm

    y -= 3 * mm
    section_title("4) Aviso legal")
    page = ensure_space(35 * mm, page)

    aviso = (
        "Este informe es informativo y se genera mediante reglas automatizadas (MVP). "
        "No constituye asesoramiento jurídico personalizado. "
        "Para un análisis completo y/o redacción contractual final, consulta con un profesional o usa la versión Pro."
    )
    c.setFont("Helvetica", 9)
    for line in wrap2(aviso, max_chars=110):
        c.drawString(left, y, line)
        y -= 4.8 * mm

    c.showPage()
    c.save()

    out = buf.getvalue()
    buf.close()
    return out


# ============================================================
# PDF GENERATOR (CONTRATO ALQUILER MVP)
# ============================================================
def generar_pdf_contrato_alquiler(data: dict) -> bytes:
    def wrap(texto: str, max_chars: int = 105) -> list[str]:
        words = (texto or "").split()
        lines, cur = [], ""
        for w in words:
            if len(cur) + len(w) + 1 <= max_chars:
                cur = (cur + " " + w).strip()
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    left = 18 * mm
    right = w - 18 * mm
    top = h - 18 * mm
    y = top

    def header():
        nonlocal y
        c.setFont("Helvetica-Bold", 16)
        c.drawString(left, top, "Lexia360")
        c.setFont("Helvetica", 10)
        c.drawRightString(right, top, "Contrato de Arrendamiento (MVP)")
        c.setLineWidth(1)
        c.line(left, top - 6 * mm, right, top - 6 * mm)
        y = top - 14 * mm

    def ensure(min_y: float):
        nonlocal y
        if y < min_y:
            c.showPage()
            header()

    def h2(t: str):
        nonlocal y
        ensure(40 * mm)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(left, y, t)
        y -= 7 * mm
        c.setStrokeGray(0.85)
        c.setLineWidth(0.6)
        c.line(left, y, right, y)
        c.setStrokeGray(0)
        y -= 8 * mm

    def p(texto: str):
        nonlocal y
        c.setFont("Helvetica", 10)
        for line in wrap(texto, 110):
            ensure(22 * mm)
            c.drawString(left, y, line)
            y -= 5.2 * mm
        y -= 2.5 * mm

    header()

    c.setFont("Helvetica-Bold", 14)
    c.drawString(left, y, "CONTRATO DE ARRENDAMIENTO (MVP)")
    y -= 10 * mm

    h2("1) Partes")
    p(f"Arrendador: {data['arrendador_nombre']} (DNI/NIE: {data['arrendador_dni']}).")
    p(f"Arrendatario: {data['arrendatario_nombre']} (DNI/NIE: {data['arrendatario_dni']}).")

    h2("2) Objeto e inmueble")
    p(f"Inmueble sito en: {data.get('direccion','—')}, {data.get('municipio','—')}, {data.get('comunidad_autonoma','—')}.")
    if data.get("codigo_postal"):
        p(f"Código Postal: {data.get('codigo_postal')}.")
    if data.get("superficie_m2"):
        p(f"Superficie aproximada: {data.get('superficie_m2')} m².")

    h2("3) Duración")
    p(f"El contrato comienza el {data['fecha_inicio']} y tendrá una duración inicial de {data['duracion_meses']} meses, salvo prórrogas y normativa aplicable.")

    h2("4) Renta y fianza")
    p(f"Renta mensual: {data['renta_mensual']} €.")
    p(f"Fianza: {data['fianza']} €.")
    if data.get("cuenta_pago"):
        p(f"Forma de pago: transferencia a la cuenta {data['cuenta_pago']}.")

    h2("5) Cláusulas esenciales (MVP)")
    p("a) Conservación: el arrendatario cuidará el inmueble y comunicará incidencias.")
    p("b) Gastos y suministros: se asignarán conforme a pacto entre las partes y la normativa aplicable.")
    p("c) Subarriendo/cesión: prohibido salvo autorización expresa por escrito del arrendador.")
    p("d) Protección de datos: las partes se comprometen a tratar los datos conforme a la normativa aplicable.")

    if data.get("observaciones"):
        h2("6) Observaciones")
        p(data["observaciones"])

    h2("7) Firma")
    p("En prueba de conformidad, las partes firman el presente documento en la fecha indicada.")
    p("Arrendador: ______________________    Arrendatario: ______________________")

    c.showPage()
    c.save()
    out = buf.getvalue()
    buf.close()
    return out


# ============================================================
# DOWNLOAD TOKEN (DOCUMENTS)
# ============================================================
def create_download_token(doc_id: int, minutes: int = 30) -> str:
    expire = datetime.utcnow() + timedelta(minutes=minutes)
    payload = {"doc": doc_id, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_download_token(token: str) -> int:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        doc_id = payload.get("doc")
        if not doc_id:
            raise HTTPException(status_code=401, detail="Token de descarga inválido")
        return int(doc_id)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token de descarga inválido")


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


# ============================================================
# ROUTES (STATUS) - NO FALLA + CAMPOS PARA DASHBOARD
# ============================================================
@app.get("/status")
def status(user: Usuario = Depends(get_current_user)):
    with Session(engine, expire_on_commit=False) as session:
        users_count = scalar_count(session.exec(text("SELECT COUNT(*) FROM usuario")).one())
        zonas_count = scalar_count(session.exec(text("SELECT COUNT(*) FROM zonatensionada")).one())

        inm_activos = scalar_count(session.exec(text(
            "SELECT COUNT(*) FROM inmueble WHERE id_usuario = :uid AND activo = TRUE"
        ), {"uid": user.id_usuario}).one())

        inm_trash = scalar_count(session.exec(text(
            "SELECT COUNT(*) FROM inmueble WHERE id_usuario = :uid AND activo = FALSE"
        ), {"uid": user.id_usuario}).one())

        docs = scalar_count(session.exec(text(
            "SELECT COUNT(*) FROM document WHERE id_usuario = :uid"
        ), {"uid": user.id_usuario}).one())

        return {
            "status": "✅ OK",
            "usuarios_registrados": int(users_count or 0),
            "zonas_tensionadas": int(zonas_count or 0),
            "inmuebles_activos": int(inm_activos or 0),
            "inmuebles_eliminados": int(inm_trash or 0),
            "documentos": int(docs or 0),
            "version": APP_VERSION,
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
        raise HTTPException(status_code=500, detail="ADMIN_BOOTSTRAP_SECRET vacío.")
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
        return {"ok": True, "id_zona": z.id_zona}

@app.get("/admin/zonas-tensionadas")
def listar_zonas(admin: Usuario = Depends(require_admin)):
    with Session(engine, expire_on_commit=False) as session:
        zonas = session.exec(select(ZonaTensionada).order_by(ZonaTensionada.comunidad_autonoma, ZonaTensionada.municipio)).all()
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
@app.get("/inmuebles/trash")
def listar_papelera(user: Usuario = Depends(get_current_user)):
    with Session(engine, expire_on_commit=False) as session:
        inmuebles = session.exec(
            select(Inmueble)
            .where(Inmueble.id_usuario == user.id_usuario)
            .where(Inmueble.activo == False)
            .order_by(Inmueble.id_inmueble.desc())
        ).all()
        return [inmueble_to_out(session, inm) for inm in inmuebles]

@app.post("/inmuebles/{id_inmueble}/restore")
def restaurar_inmueble(id_inmueble: int, user: Usuario = Depends(get_current_user)):
    with Session(engine, expire_on_commit=False) as session:
        inm = session.exec(
            select(Inmueble)
            .where(Inmueble.id_inmueble == id_inmueble)
            .where(Inmueble.id_usuario == user.id_usuario)
            .where(Inmueble.activo == False)
        ).first()
        if not inm:
            raise HTTPException(status_code=404, detail="Inmueble no encontrado en papelera")

        inm.activo = True
        session.add(inm)
        session.commit()

    return {"ok": True, "mensaje": "✅ Inmueble restaurado"}

@app.delete("/inmuebles/{id_inmueble}/purge")
def borrar_definitivo(id_inmueble: int, user: Usuario = Depends(get_current_user)):
    with Session(engine, expire_on_commit=False) as session:
        inm = session.exec(
            select(Inmueble)
            .where(Inmueble.id_inmueble == id_inmueble)
            .where(Inmueble.id_usuario == user.id_usuario)
            .where(Inmueble.activo == False)
        ).first()

        if not inm:
            raise HTTPException(status_code=404, detail="Solo se puede borrar definitivo desde la papelera")

        session.exec(text("DELETE FROM rulerun WHERE id_inmueble = :iid"), {"iid": id_inmueble})
        session.delete(inm)
        session.commit()

    return {"ok": True, "mensaje": "🧨 Borrado definitivo completado"}

@app.post("/inmuebles")
def crear_inmueble(payload: InmuebleCreate, user: Usuario = Depends(get_current_user)):
    try:
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
                activo=True,
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

            return {"ok": True, "mensaje": "✅ Inmueble creado", "id_inmueble": inm.id_inmueble, "version": APP_VERSION}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"INMUEBLE_CREATE_ERROR: {type(e).__name__}: {str(e)}")

@app.get("/inmuebles")
def listar_inmuebles(user: Usuario = Depends(get_current_user)):
    with Session(engine, expire_on_commit=False) as session:
        inmuebles = session.exec(
            select(Inmueble)
            .where(Inmueble.id_usuario == user.id_usuario)
            .where(Inmueble.activo == True)
            .order_by(Inmueble.id_inmueble.desc())
        ).all()
        return [inmueble_to_out(session, inm) for inm in inmuebles]

@app.get("/inmuebles/{id_inmueble}")
def get_inmueble(id_inmueble: int, user: Usuario = Depends(get_current_user)):
    with Session(engine, expire_on_commit=False) as session:
        inm = session.exec(
            select(Inmueble)
            .where(Inmueble.id_inmueble == id_inmueble)
            .where(Inmueble.id_usuario == user.id_usuario)
        ).first()
        if not inm:
            raise HTTPException(status_code=404, detail="Inmueble no encontrado")
        return inmueble_to_out(session, inm)

@app.delete("/inmuebles/{id_inmueble}")
def borrar_inmueble(id_inmueble: int, user: Usuario = Depends(get_current_user)):
    with Session(engine, expire_on_commit=False) as session:
        inm = session.exec(
            select(Inmueble)
            .where(Inmueble.id_inmueble == id_inmueble)
            .where(Inmueble.id_usuario == user.id_usuario)
            .where(Inmueble.activo == True)
        ).first()
        if not inm:
            raise HTTPException(status_code=404, detail="Inmueble no encontrado")
        inm.activo = False
        session.add(inm)
        session.commit()
    return {"ok": True, "mensaje": "✅ Inmueble movido a papelera"}

@app.get("/inmuebles/{id_inmueble}/pdf")
def inmueble_pdf(id_inmueble: int, user: Usuario = Depends(get_current_user)):
    with Session(engine, expire_on_commit=False) as session:
        inm = session.exec(
            select(Inmueble)
            .where(Inmueble.id_inmueble == id_inmueble)
            .where(Inmueble.id_usuario == user.id_usuario)
            .where(Inmueble.activo == True)
        ).first()
        if not inm:
            raise HTTPException(status_code=404, detail="Inmueble no encontrado")
        payload = inmueble_to_out(session, inm)

    pdf_bytes = generar_pdf_informe(payload)
    filename = f"lexia360_informe_inmueble_{id_inmueble}.pdf"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)


# ============================================================
# ROUTES (DOCUMENTS)
# ============================================================
@app.post("/documents/lease")
def create_lease_document(payload: LeaseDocumentCreate, user: Usuario = Depends(get_current_user)):
    with Session(engine, expire_on_commit=False) as session:
        inm = session.exec(
            select(Inmueble)
            .where(Inmueble.id_inmueble == payload.inmueble_id)
            .where(Inmueble.id_usuario == user.id_usuario)
        ).first()
        if not inm:
            raise HTTPException(status_code=404, detail="Inmueble no encontrado")

        doc_payload = {
            "tipo": "lease",
            "titulo": "Contrato de Arrendamiento (MVP)",
            "arrendador_nombre": payload.arrendador_nombre.strip(),
            "arrendador_dni": payload.arrendador_dni.strip(),
            "arrendatario_nombre": payload.arrendatario_nombre.strip(),
            "arrendatario_dni": payload.arrendatario_dni.strip(),
            "fecha_inicio": str(payload.fecha_inicio),
            "duracion_meses": int(payload.duracion_meses),
            "renta_mensual": float(payload.renta_mensual),
            "fianza": float(payload.fianza),
            "cuenta_pago": (payload.cuenta_pago.strip() if payload.cuenta_pago else None),
            "observaciones": (payload.observaciones.strip() if payload.observaciones else None),

            "direccion": inm.direccion,
            "municipio": inm.municipio,
            "comunidad_autonoma": inm.comunidad_autonoma,
            "codigo_postal": inm.codigo_postal,
            "superficie_m2": inm.superficie_m2,
        }

        pdf = generar_pdf_contrato_alquiler(doc_payload)

        doc = Document(
            id_usuario=user.id_usuario,
            id_inmueble=inm.id_inmueble,
            tipo="lease",
            titulo="Contrato de Arrendamiento (MVP)",
            payload_json=json.dumps(doc_payload, ensure_ascii=False),
            pdf_bytes=pdf,
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

        dl_token = create_download_token(doc.id_document, minutes=60)

        return {"ok": True, "id_document": doc.id_document, "download_token": dl_token}


@app.get("/documents")
def list_documents(user: Usuario = Depends(get_current_user)):
    with Session(engine, expire_on_commit=False) as session:
        docs = session.exec(
            select(Document)
            .where(Document.id_usuario == user.id_usuario)
            .order_by(Document.id_document.desc())
        ).all()
        return [{
            "id_document": d.id_document,
            "tipo": d.tipo,
            "titulo": d.titulo,
            "id_inmueble": d.id_inmueble,
            "creado_en": d.creado_en.isoformat(),
        } for d in docs]


@app.get("/documents/{id_document}/pdf")
def download_document_pdf(id_document: int, request: Request, token: str | None = None):
    """
    Descarga:
    - con token de descarga: /documents/{id}/pdf?token=...
    - o con auth normal: Authorization: Bearer ...
    """
    with Session(engine, expire_on_commit=False) as session:
        doc = session.exec(select(Document).where(Document.id_document == id_document)).first()
        if not doc or not doc.pdf_bytes:
            raise HTTPException(status_code=404, detail="Documento no encontrado")

        if token:
            doc_id = verify_download_token(token)
            if doc_id != id_document:
                raise HTTPException(status_code=401, detail="Token no corresponde al documento")
        else:
            # auth normal
            auth = request.headers.get("authorization") or ""
            if not auth.lower().startswith("bearer "):
                raise HTTPException(status_code=401, detail="Not authenticated")
            tok = auth.split(" ", 1)[1].strip()
            try:
                payload = jwt.decode(tok, SECRET_KEY, algorithms=[ALGORITHM])
                email = payload.get("sub")
                if not email:
                    raise HTTPException(status_code=401, detail="Token inválido")
            except JWTError:
                raise HTTPException(status_code=401, detail="Token inválido")

            user = session.exec(select(Usuario).where(Usuario.email == email)).first()
            if not user or user.id_usuario != doc.id_usuario:
                raise HTTPException(status_code=403, detail="No autorizado")

        filename = f"lexia360_document_{id_document}.pdf"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(io.BytesIO(doc.pdf_bytes), media_type="application/pdf", headers=headers)


# ============================================================
# CHAT (MOCK)
# ============================================================
@app.post("/chat", response_model=ChatResponse)
def chat_assistant(payload: ChatRequest, user: Usuario = Depends(get_current_user)):
    with Session(engine, expire_on_commit=False) as session:
        inmueble = session.exec(
            select(Inmueble)
            .where(Inmueble.id_inmueble == payload.inmueble_id)
            .where(Inmueble.id_usuario == user.id_usuario)
            .where(Inmueble.activo == True)
        ).first()
        if not inmueble:
            raise HTTPException(status_code=404, detail="Inmueble no encontrado")

    respuesta, requiere_pro = mock_chat_engine(payload.mensaje)
    return {"respuesta": respuesta, "requiere_pro": requiere_pro}
