from sqlmodel import create_engine
from app.core.config import settings

engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True)

