import io
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.core.db import engine
from app.models.inmueble import Inmueble
from app.models.user import Usuario
from app.services.pdf_service import generar_pdf_informe
from app.routers.inmuebles import inmueble_to_out
from app.services.audit_service import log_action

router = APIRouter(prefix="/documents", tags=["documents"])

@router.get("/inmuebles/{id_inmueble:int}/pdf")
def inmueble_pdf(id_inmueble: int, request: Request, user: Usuario = Depends()):
    with Session(engine) as session:
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

        log_action(
            session,
            accion="PDF_DOWNLOAD",
            id_usuario=user.id_usuario,
            entidad="inmueble",
            entidad_id=str(id_inmueble),
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        session.commit()

    filename = f"lexia360_informe_inmueble_{id_inmueble}.pdf"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)

