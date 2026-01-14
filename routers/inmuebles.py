import json
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select
from sqlalchemy import text

from app.core.db import engine
from app.models.inmueble import Inmueble
from app.models.rulerun import RuleRun
from app.models.user import Usuario
from app.schemas.inmuebles import InmuebleCreate
from app.services.rules_engine import evaluar_reglas
from app.services.audit_service import log_action

router = APIRouter(prefix="/inmuebles", tags=["inmuebles"])

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

# ✅ IMPORTANTE: rutas “trash” antes de /{id}
@router.get("/trash")
def listar_papelera(user: Usuario = Depends()):
    with Session(engine) as session:
        inmuebles = session.exec(
            select(Inmueble)
            .where(Inmueble.id_usuario == user.id_usuario)
            .where(Inmueble.activo == False)
            .order_by(Inmueble.id_inmueble.desc())
        ).all()
        return [inmueble_to_out(session, inm) for inm in inmuebles]

@router.post("")
def crear_inmueble(payload: InmuebleCreate, request: Request, user: Usuario = Depends()):
    fecha_analisis = date.today()
    with Session(engine) as session:
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

        log_action(
            session,
            accion="INMUEBLE_CREATE",
            id_usuario=user.id_usuario,
            entidad="inmueble",
            entidad_id=str(inm.id_inmueble),
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        session.commit()

        return inmueble_to_out(session, inm)

@router.get("")
def listar_inmuebles(user: Usuario = Depends()):
    with Session(engine) as session:
        inmuebles = session.exec(
            select(Inmueble)
            .where(Inmueble.id_usuario == user.id_usuario)
            .where(Inmueble.activo == True)
            .order_by(Inmueble.id_inmueble.desc())
        ).all()
        return [inmueble_to_out(session, inm) for inm in inmuebles]

@router.get("/{id_inmueble:int}")
def get_inmueble(id_inmueble: int, user: Usuario = Depends()):
    with Session(engine) as session:
        inm = session.exec(
            select(Inmueble)
            .where(Inmueble.id_inmueble == id_inmueble)
            .where(Inmueble.id_usuario == user.id_usuario)
            .where(Inmueble.activo == True)
        ).first()
        if not inm:
            raise HTTPException(status_code=404, detail="Inmueble no encontrado")
        return inmueble_to_out(session, inm)

@router.delete("/{id_inmueble:int}")
def borrar_inmueble(id_inmueble: int, request: Request, user: Usuario = Depends()):
    with Session(engine) as session:
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

        log_action(
            session,
            accion="INMUEBLE_TRASH",
            id_usuario=user.id_usuario,
            entidad="inmueble",
            entidad_id=str(id_inmueble),
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        session.commit()

    return {"ok": True, "mensaje": "✅ Inmueble movido a papelera"}

@router.post("/{id_inmueble:int}/restore")
def restaurar_inmueble(id_inmueble: int, request: Request, user: Usuario = Depends()):
    with Session(engine) as session:
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

        log_action(
            session,
            accion="INMUEBLE_RESTORE",
            id_usuario=user.id_usuario,
            entidad="inmueble",
            entidad_id=str(id_inmueble),
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        session.commit()

    return {"ok": True, "mensaje": "✅ Inmueble restaurado"}

@router.delete("/{id_inmueble:int}/purge")
def borrar_definitivo(id_inmueble: int, request: Request, user: Usuario = Depends()):
    with Session(engine) as session:
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

        log_action(
            session,
            accion="INMUEBLE_PURGE",
            id_usuario=user.id_usuario,
            entidad="inmueble",
            entidad_id=str(id_inmueble),
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        session.commit()

    return {"ok": True, "mensaje": "🧨 Borrado definitivo completado"}

