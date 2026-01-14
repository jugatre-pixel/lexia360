from datetime import datetime, date
from sqlmodel import SQLModel, Field
from app.core.config import settings

class RuleRun(SQLModel, table=True):
    id_run: int | None = Field(default=None, primary_key=True)
    id_inmueble: int = Field(index=True, foreign_key="inmueble.id_inmueble")

    version: str = settings.app_version
    creado_en: datetime = Field(default_factory=datetime.utcnow)

    fecha_analisis: date
    resultados_json: str
    alertas_json: str

