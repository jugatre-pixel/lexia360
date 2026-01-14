from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from app.core.db import engine
from app.core.security import validate_password, get_password_hash, verify_password, create_access_token
from app.schemas.auth import RegisterPayload
from app.models.user import Usuario

router = APIRouter()

@router.post("/register")
def register(payload: RegisterPayload):
    validate_password(payload.password)
    with Session(engine) as session:
        existing = session.exec(select(Usuario).where(Usuario.email == payload.email)).first()
        if existing:
            raise HTTPException(status_code=400, detail="El usuario ya existe")

        user = Usuario(
            nombre=payload.nombre,
            email=payload.email,
            hashed_password=get_password_hash(payload.password),
            rol="cliente",
        )
        session.add(user)
        session.commit()
    return {"mensaje": "✅ Registro completado"}

@router.post("/token")
def login(form: OAuth2PasswordRequestForm = Depends()):
    with Session(engine) as session:
        user = session.exec(select(Usuario).where(Usuario.email == form.username)).first()
        if not user or not verify_password(form.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    token = create_access_token(form.username)
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me")
def me(user: Usuario = Depends(lambda: None)):
    # Este endpoint se implementa en main con dependency real (para evitar circular import)
    raise HTTPException(status_code=500, detail="Misconfigured /me (should be overridden)")

