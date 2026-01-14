from datetime import datetime
from sqlmodel import SQLModel, Field

class Usuario(SQLModel, table=True):
    id_usuario: int | None = Field(default=None, primary_key=True)
    nombre: str
    email: str = Field(index=True)
    hashed_password: str
    rol: str = "cliente"
    creado_en: datetime = Field(default_factory=datetime.utcnow)

