from datetime import datetime
from sqlmodel import SQLModel, Field

class AuditLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    id_usuario: int | None = Field(default=None, index=True)

    accion: str
    entidad: str | None = None
    entidad_id: str | None = None

    ip: str | None = None
    user_agent: str | None = None

    meta_json: str | None = None
    creado_en: datetime = Field(default_factory=datetime.utcnow)

