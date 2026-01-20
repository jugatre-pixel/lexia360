from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi import HTTPException
from passlib.context import CryptContext
import logging

from core.config import settings

logger = logging.getLogger("core.security")

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def validate_password(password: str):
    if not password or len(password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(email: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=getattr(settings, "access_token_expire_minutes", 60))
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=getattr(settings, "algorithm", "HS256"))

def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[getattr(settings, "algorithm", "HS256")])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Token inválido")
        return email
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")
