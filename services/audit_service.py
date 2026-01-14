import json
from sqlmodel import Session
from app.models.audit import AuditLog

def log_action(
    session: Session,
    accion: str,
    id_usuario: int | None,
    entidad: str | None = None,
    entidad_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    meta: dict | None = None,
):
    entry = AuditLog(
        accion=accion,
        id_usuario=id_usuario,
        entidad=entidad,
        entidad_id=entidad_id,
        ip=ip,
        user_agent=user_agent,
        meta_json=json.dumps(meta, ensure_ascii=False) if meta else None,
    )
    session.add(entry)

