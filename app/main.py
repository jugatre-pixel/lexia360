import os
import json
import traceback
import secrets
import io
from datetime import datetime, timedelta, date
from typing import Optional, Tuple

from fastapi import FastAPI, HTTPException, Depends, Request, Response, Query
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
APP_VERSION = os.getenv("APP_VERSION", "lexia360-v16-documents-checklist")

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

# ✅ CRÍTICO: esto va en CONFIG, global
PDF_TOKEN_EXPIRE_MINUTES = int(os.getenv("PDF_TOKEN_EXPIRE_MINUTES", "10"))

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").strip()
ALLOW_ORIGINS = ["*"] if CORS_ORIGINS == "*" else [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

# Hash robusto (evita líos con bcrypt)
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# ✅ auto_error=False para permitir endpoints PDF con token ?t=... sin Authorization
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


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


# Static mount (carpeta ./static en raíz del repo)
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

    tipo: str = Field(index=True)  # "lease", "burofax", etc.
    titulo: str
    estado: str = Field(default="generado")  # generado | firmado | archivado

    payload_json: str = Field(default="{}")
    creado_en: datetime = Field(default_factory=datetime.utcnow)


class ChecklistItem(SQLModel, table=True):
    id_item: int | None = Field(default=None, primary_key=True)
    id_document: int = Field(index=True, foreign_key="document.id_document")

    titulo: str
    descripcion: str | None = None
    completado: bool = Field(default=False, index=True)

    creado_en: datetime = Field(default_factory=datetime.utcnow)
    completado_en: datetime | None = None


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


class LeaseCreate(BaseModel):
    inmueble_id: int
    arrendatario_nombre: str | None = None
    arrendatario_dni: str | None = None
    fecha_inicio: date | None = None
    duracion_meses: int | None = None


# ============================================================
# STARTUP + AUTO FIX SCHEMA
# ============================================================
def _autofix_schema():
    """
    No sustituye Alembic, pero evita roturas típicas en MVP.
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

        # document.payload_json (si document existía sin esa columna)
        exists_doc_payload = conn.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name='document' AND column_name='payload_json'
        """)).first()
        if exists_doc_payload and not exists_doc_payload:
            conn.execute(text("ALTER TABLE document ADD COLUMN payload_json TEXT DEFAULT '{}'"))
            # document.estado
            exists_doc_estado = conn.execute(text("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name='document' AND column_name='estado'
            """)).first()
            if not exists_doc_estado:
                conn.execute(text("ALTER TABLE document ADD COLUMN estado VARCHAR(32) DEFAULT 'generado'"))
                conn.execute(text("UPDATE document SET estado = 'generado' WHERE estado IS NULL"))
                conn.execute(text("ALTER TABLE document ALTER COLUMN estado SET NOT NULL"))

            # document.titulo
            exists_doc_titulo = conn.execute(text("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name='document' AND column_name='titulo'
            """)).first()
            if not exists_doc_titulo:
                conn.execute(text("ALTER TABLE document ADD COLUMN titulo TEXT DEFAULT ''"))
                conn.execute(text("UPDATE document SET titulo = '' WHERE titulo IS NULL"))
                conn.execute(text("ALTER TABLE document ALTER COLUMN titulo SET NOT NULL"))

            # document.tipo
            exists_doc_tipo = conn.execute(text("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name='document' AND column_name='tipo'
            """)).first()
            if not exists_doc_tipo:
                conn.execute(text("ALTER TABLE document ADD COLUMN tipo VARCHAR(64) DEFAULT 'lease'"))
                conn.execute(text("UPDATE document SET tipo = 'lease' WHERE tipo IS NULL"))
                conn.execute(text("ALTER TABLE document ALTER COLUMN tipo SET NOT NULL"))

            # document.id_inmueble (por si la tabla se creó sin FK)
            exists_doc_inm = conn.execute(text("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name='document' AND column_name='id_inmueble'
            """)).first()
            if not exists_doc_inm:
                conn.execute(text("ALTER TABLE document ADD COLUMN id_inmueble INTEGER NULL"))


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


# ✅ CRÍTICO: create_access_token bien (sin funciones anidadas)
def create_access_token(email: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_pdf_token(user_id: int, inmueble_id: int) -> str:
    expire = datetime.utcnow() + timedelta(minutes=PDF_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": f"pdf:{user_id}:{inmueble_id}", "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_pdf_token(token: str) -> Optional[Tuple[int, int]]:
    """
    Devuelve (user_id, inmueble_id) si es válido, si no None.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub", "")
        if not sub.startswith("pdf:"):
            return None
        parts = sub.split(":")
        if len(parts) != 3:
            return None
        uid = int(parts[1])
        iid = int(parts[2])
        return uid, iid
    except Exception:
        return None


def get_current_user(token: str | None = Depends(oauth2_scheme)) -> Usuario:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email or str(email).startswith("pdf:"):
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
# HELPERS (OUT)
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


def document_to_out(session: Session, doc: Document) -> dict:
    items = session.exec(
        select(ChecklistItem).where(ChecklistItem.id_document == doc.id_document).order_by(ChecklistItem.id_item.asc())
    ).all()

    return {
        "id_document": doc.id_document,
        "id_usuario": doc.id_usuario,
        "id_inmueble": doc.id_inmueble,
        "tipo": doc.tipo,
        "titulo": doc.titulo,
        "estado": doc.estado,
        "creado_en": doc.creado_en.isoformat(),
        "payload": json.loads(doc.payload_json or "{}"),
        "checklist": [{
            "id_item": it.id_item,
            "titulo": it.titulo,
            "descripcion": it.descripcion,
            "completado": it.completado,
            "creado_en": it.creado_en.isoformat(),
            "completado_en": it.completado_en.isoformat() if it.completado_en else None
        } for it in items]
    }


# ============================================================
# PDF GENERATOR (INMUEBLE INFORME)
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
    for a in alertas:
        page = ensure_space(28 * mm, page)
        for line in wrap(f"• {a}", max_chars=110):
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
    for line in wrap(aviso, max_chars=110):
        c.drawString(left, y, line)
        y -= 4.8 * mm

    c.showPage()
    c.save()

    out = buf.getvalue()
    buf.close()
    return out


# ============================================================
# PDF GENERATOR (LEASE CONTRACT)
# ============================================================
def generar_pdf_contrato_arrendamiento(doc: dict, inmueble: dict) -> bytes:
    payload = doc.get("payload") or {}
    arr_nom = payload.get("arrendatario_nombre") or "________________________"
    arr_dni = payload.get("arrendatario_dni") or "________________________"
    fecha_ini = payload.get("fecha_inicio") or str(date.today())
    dur = payload.get("duracion_meses") or 12

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    left = 18 * mm
    right = w - 18 * mm
    y = h - 20 * mm

    def line(txt, size=10, bold=False, gap=5.2):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(left, y, txt)
        y -= gap * mm

    def hr():
        nonlocal y
        c.setLineWidth(0.7)
        c.setStrokeGray(0.8)
        c.line(left, y, right, y)
        c.setStrokeGray(0)
        y -= 8 * mm

    line("LEXIA360", 16, bold=True, gap=7)
    line("Contrato de arrendamiento (MVP)", 12, bold=True, gap=7)
    line(f"Documento ID: {doc.get('id_document')}", 9, gap=5)
    line(f"Generado: {doc.get('creado_en')}", 9, gap=5)
    hr()

    line("1) Partes", 11, bold=True, gap=6.2)
    line("Arrendador: __________________________", 10, gap=5.2)
    line(f"Arrendatario: {arr_nom}", 10, gap=5.2)
    line(f"DNI/NIE: {arr_dni}", 10, gap=5.2)
    hr()

    line("2) Inmueble objeto del contrato", 11, bold=True, gap=6.2)
    line(f"Dirección: {inmueble.get('direccion')}", 10, gap=5.2)
    line(f"Municipio: {inmueble.get('municipio')} · {inmueble.get('comunidad_autonoma')}", 10, gap=5.2)
    line(f"CP: {inmueble.get('codigo_postal') or '—'} · Superficie: {inmueble.get('superficie_m2') or '—'} m²", 10, gap=5.2)
    hr()

    line("3) Condiciones económicas", 11, bold=True, gap=6.2)
    line(f"Renta: {inmueble.get('renta_propuesta')} € / mes", 10, gap=5.2)
    line("Fianza: 1 mensualidad (MVP)", 10, gap=5.2)
    hr()

    line("4) Duración", 11, bold=True, gap=6.2)
    line(f"Inicio: {fecha_ini}", 10, gap=5.2)
    line(f"Duración: {dur} meses (MVP)", 10, gap=5.2)
    hr()

    line("5) Aviso", 11, bold=True, gap=6.2)
    line("Este documento es un borrador MVP. No constituye asesoramiento jurídico personalizado.", 9, gap=4.8)
    line("Sprint siguiente: cláusulas completas + anexos + checklist validado.", 9, gap=4.8)

    c.showPage()
    c.save()

    out = buf.getvalue()
    buf.close()
    return out


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
        def scalar(q: str) -> int:
            v = session.exec(text(q)).one()
            if isinstance(v, int):
                return int(v)
            return int(v[0])

        users_count = scalar("SELECT COUNT(*) FROM usuario")
        zonas_count = scalar("SELECT COUNT(*) FROM zonatensionada")
        inm_activos = scalar("SELECT COUNT(*) FROM inmueble WHERE activo = TRUE")
        inm_trash = scalar("SELECT COUNT(*) FROM inmueble WHERE activo = FALSE")

        try:
            docs_count = scalar("SELECT COUNT(*) FROM document")
        except Exception:
            docs_count = 0

        return {
            "status": "✅ OK",
            "usuarios_registrados": users_count,
            "zonas_tensionadas": zonas_count,
            "inmuebles_activos": inm_activos,
            "inmuebles_eliminados": inm_trash,
            "documentos": docs_count,
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


# ✅ alias por compatibilidad con tu HTML
@app.delete("/inmuebles/{id_inmueble}/hard")
def borrar_definitivo_alias(id_inmueble: int, user: Usuario = Depends(get_current_user)):
    return borrar_definitivo(id_inmueble, user)


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
            .where(Inmueble.activo == True)
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


@app.get("/inmuebles/{id_inmueble}/pdf-token")
def inmueble_pdf_token(id_inmueble: int, user: Usuario = Depends(get_current_user)):
    with Session(engine, expire_on_commit=False) as session:
        inm = session.exec(
            select(Inmueble)
            .where(Inmueble.id_inmueble == id_inmueble)
            .where(Inmueble.id_usuario == user.id_usuario)
            .where(Inmueble.activo == True)
        ).first()
        if not inm:
            raise HTTPException(status_code=404, detail="Inmueble no encontrado")

    t = create_pdf_token(user.id_usuario, id_inmueble)
    return {"token": t, "expires_minutes": PDF_TOKEN_EXPIRE_MINUTES}


@app.get("/inmuebles/{id_inmueble}/pdf")
def inmueble_pdf(
    id_inmueble: int,
    t: str | None = Query(default=None),
    bearer: str | None = Depends(oauth2_scheme),
):
    """
    Descarga PDF:
    - Con Authorization Bearer normal -> OK
    - Sin Authorization, usando token en query ?t=... -> OK
    """
    if bearer:
        user = get_current_user(bearer)
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
    else:
        if not t:
            raise HTTPException(status_code=401, detail="Not authenticated")
        decoded = decode_pdf_token(t)
        if not decoded:
            raise HTTPException(status_code=401, detail="Token PDF inválido o caducado")
        uid, iid = decoded
        if iid != id_inmueble:
            raise HTTPException(status_code=401, detail="Token PDF no corresponde a este inmueble")

        with Session(engine, expire_on_commit=False) as session:
            inm = session.exec(
                select(Inmueble)
                .where(Inmueble.id_inmueble == id_inmueble)
                .where(Inmueble.id_usuario == uid)
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
# ROUTES (DOCUMENTS + CHECKLIST)
# ============================================================
class ChecklistUpdate(BaseModel):
    completado: bool


@app.patch("/documents/{id_document}/checklist/{id_item}")
def update_checklist_item(
    id_document: int,
    id_item: int,
    payload: ChecklistUpdate,
    user: Usuario = Depends(get_current_user)
):
    with Session(engine, expire_on_commit=False) as session:
        # Verifica doc del usuario
        doc = session.exec(
            select(Document)
            .where(Document.id_document == id_document)
            .where(Document.id_usuario == user.id_usuario)
        ).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Documento no encontrado")

        # Item del doc
        item = session.exec(
            select(ChecklistItem)
            .where(ChecklistItem.id_item == id_item)
            .where(ChecklistItem.id_document == id_document)
        ).first()
        if not item:
            raise HTTPException(status_code=404, detail="Item de checklist no encontrado")

        item.completado = bool(payload.completado)
        item.completado_en = datetime.utcnow() if item.completado else None

        session.add(item)
        session.commit()
        session.refresh(item)

        return {
            "ok": True,
            "id_item": item.id_item,
            "id_document": item.id_document,
            "completado": item.completado,
            "completado_en": item.completado_en.isoformat() if item.completado_en else None
        }


@app.post("/documents/lease")
def create_lease_document(payload: LeaseCreate, user: Usuario = Depends(get_current_user)):
    with Session(engine, expire_on_commit=False) as session:
        inm = session.exec(
            select(Inmueble)
            .where(Inmueble.id_inmueble == payload.inmueble_id)
            .where(Inmueble.id_usuario == user.id_usuario)
            .where(Inmueble.activo == True)
        ).first()
        if not inm:
            raise HTTPException(status_code=404, detail="Inmueble no encontrado")

        doc = Document(
            id_usuario=user.id_usuario,
            id_inmueble=inm.id_inmueble,
            tipo="lease",
            titulo="Contrato de arrendamiento (MVP)",
            estado="generado",
            payload_json=json.dumps(payload.model_dump(), ensure_ascii=False, default=str),
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

        base_items = [
            ("Verificar identidad del arrendatario", "DNI/NIE en vigor y coincidencia de datos."),
            ("Comprobar titularidad / autorización", "Nota simple o autorización si no es titular."),
            ("Inventario y estado de la vivienda", "Fotos + listado de enseres (si aplica)."),
            ("Entrega de llaves", "Acta de entrega / recepción."),
            ("Depósito de fianza", "Gestión conforme normativa autonómica (si aplica)."),
        ]
        for t_, d_ in base_items:
            session.add(ChecklistItem(
                id_document=doc.id_document,
                titulo=t_,
                descripcion=d_
            ))
        session.commit()

        return {
            "ok": True,
            "id_document": doc.id_document,
            "id_inmueble": doc.id_inmueble,
            "tipo": doc.tipo,
            "titulo": doc.titulo,
            "version": APP_VERSION
        }


@app.get("/documents/{id_document}")
def get_document(id_document: int, user: Usuario = Depends(get_current_user)):
    with Session(engine, expire_on_commit=False) as session:
        doc = session.exec(
            select(Document)
            .where(Document.id_document == id_document)
            .where(Document.id_usuario == user.id_usuario)
        ).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        return document_to_out(session, doc)


@app.get("/documents/{id_document}/pdf")
def get_document_pdf(id_document: int, user: Usuario = Depends(get_current_user)):
    with Session(engine, expire_on_commit=False) as session:
        doc = session.exec(
            select(Document)
            .where(Document.id_document == id_document)
            .where(Document.id_usuario == user.id_usuario)
        ).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Documento no encontrado")

        inm_payload = {}
        if doc.id_inmueble:
            inm = session.exec(
                select(Inmueble)
                .where(Inmueble.id_inmueble == doc.id_inmueble)
                .where(Inmueble.id_usuario == user.id_usuario)
            ).first()
            if inm:
                inm_payload = inmueble_to_out(session, inm)

        doc_out = document_to_out(session, doc)

    if doc.tipo == "lease":
        pdf_bytes = generar_pdf_contrato_arrendamiento(doc_out, inm_payload)
        filename = f"lexia360_contrato_arrendamiento_{id_document}.pdf"
    else:
        pdf_bytes = b"%PDF-1.4\n% Lexia360 placeholder\n"
        filename = f"lexia360_document_{id_document}.pdf"

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)

# ============================================================
# ROUTES (DOCUMENTS LIST) ✅ NUEVO
# ============================================================
@app.get("/documents")
def list_documents(
    inmueble_id: int | None = None,
    user: Usuario = Depends(get_current_user)
):
    """
    Lista documentos del usuario.
    Opcional: filtrar por inmueble_id.
    """
    with Session(engine, expire_on_commit=False) as session:
        q = select(Document).where(Document.id_usuario == user.id_usuario)
        if inmueble_id is not None:
            q = q.where(Document.id_inmueble == inmueble_id)
        docs = session.exec(q.order_by(Document.id_document.desc()).limit(50)).all()

        out = []
        for d in docs:
            # checklist count rápido
            total = session.exec(
                text("SELECT COUNT(*) FROM checklistitem WHERE id_document = :id"),
                {"id": d.id_document}
            ).one()
            if not isinstance(total, int):
                total = total[0]

            done = session.exec(
                text("SELECT COUNT(*) FROM checklistitem WHERE id_document = :id AND completado = TRUE"),
                {"id": d.id_document}
            ).one()
            if not isinstance(done, int):
                done = done[0]

            out.append({
                "id_document": d.id_document,
                "id_inmueble": d.id_inmueble,
                "tipo": d.tipo,
                "titulo": d.titulo,
                "estado": d.estado,
                "creado_en": d.creado_en.isoformat(),
                "checklist_total": int(total),
                "checklist_done": int(done),
            })

        return out


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
