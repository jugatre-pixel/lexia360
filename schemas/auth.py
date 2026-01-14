
from pydantic import BaseModel, EmailStr

class RegisterPayload(BaseModel):
    nombre: str
    email: EmailStr
    password: str
