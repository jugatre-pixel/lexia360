from sqlmodel import SQLModel, create_engine, Session
from app.core.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)


def init_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine, expire_on_commit=False) as session:
        yield session
