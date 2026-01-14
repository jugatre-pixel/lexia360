import os
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.core.security import decode_token
from app.core.logging import catch_exceptions

from app.models.user import Usuario
from app.routers import auth as auth_router
from app.routers import inmuebles as inmuebles_router
from app.routers import zonas as zonas_router
from app.routers import documents as documents_router

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

app = FastAPI(title="Lexia360", version=settings.app_version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(catch_exceptions)

# Static
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static", html=True), name="static")

def get_current_user(token: str = Depends(oauth2_scheme)) -> Usuario:
    email = decode_token(token)
    with Session(engine) as session:
        user = session.exec(select(Usuario).where(Usuario.email == email)).first()
        if not user:
            raise HTTPException(status_code=401, detail="Usuario no existe")
        return user

def require_admin(user: Usuario = Depends(get_current_user)) -> Usuario:
    if user.rol != "admin":
        raise HTTPException(status_code=403, detail="No autorizado (admin)")
    return user

# Public
@app.get("/")
def root():
    return {"mensaje": "Lexia360 API OK 🚀", "static": "/static/index.html", "version": settings.app_version}

@app.head("/")
def head_root():
    return Response(status_code=200)

@app.get("/version")
def version():
    return {"version": settings.app_version}

@app.get("/status")
def status():
    with Session(engine) as session:
        users_count = session.exec(select(Usuario)).all()
        return {"status": "✅ OK", "usuarios_registrados": len(users_count), "version": settings.app_version}

# Auth routes
app.include_router(auth_router.router)

# Override /me here (real)
@app.get("/me")
def me(user: Usuario = Depends(get_current_user)):
    return {"id_usuario": user.id_usuario, "email": user.email, "rol": user.rol, "version": settings.app_version}

# Mount routers with dependencies injected
# Trick: we set dependency overrides per-router by re-declaring Depends in router definitions using Depends() placeholder.
# We bind them here using dependency_overrides on the app.

app.dependency_overrides[lambda: None] = get_current_user  # for auth_router /me placeholder (not used directly)

# Routers
# Inject user dependency by overriding Depends() in those routers:
inmuebles_router.router.dependencies = [Depends(get_current_user)]
documents_router.router.dependencies = [Depends(get_current_user)]

app.include_router(inmuebles_router.router)
app.include_router(zonas_router.router)
app.include_router(documents_router.router)
