from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from datetime import date

from app.core.db import engine
from app.schemas.zonas import ZonaCreate
from app.models.zona import ZonaTensionada
from app.models.user import Usuario

router = APIRouter()

def require_admin(user: Usuario) -> Usuario:
    if user.rol != "admin":
        raise Exception("No autorizado (admin)")
    return user

@router.get("/zonas-tensionadas/check")
def check_zona(municipio: str, comunidad_autonoma: str, fecha: date | None = None):
    f = fecha or date.today()
    with Session(engine) as session:
        zona = session.exec(
            select(ZonaTensionada)
            .where(ZonaTensionada.municipio == municipio.strip())
            .where(ZonaTensionada.comunidad_autonoma == comunidad_autonoma.strip())
            .where(ZonaTensionada.fecha_inicio <= f)
            .where((ZonaTensionada.fecha_fin == None) | (ZonaTensionada.fecha_fin >= f))
            .where(ZonaTensionada.activo == True)
            .order_by(ZonaTensionada.fecha_inicio.desc())
        ).first()
        return {
            "municipio": municipio,
            "comunidad_autonoma": comunidad_autonoma,
            "fecha": str(f),
            "zona_tensionada": zona is not None,
            "fuente_oficial": zona.fuente_oficial if zona else None,
        }

