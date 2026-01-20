import os
import logging
import secrets

class Settings:
    app_name: str = "Lexia360"
    app_version: str = os.getenv("APP_VERSION", "lexia360-sprint1-modular-alembic")
    algorithm: str = os.getenv("ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    database_url: str
    secret_key: str

    def __init__(self):
        # Allow a sensible default for local development/tests
        db = os.getenv("DATABASE_URL", "").strip()
        if not db:
            logging.warning("DATABASE_URL not set, defaulting to sqlite:///:memory: (not for production)")
            self.database_url = "sqlite:///:memory:"
        else:
            self.database_url = db

        if self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql+psycopg2://", 1)
        if self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

        sk = os.getenv("SECRET_KEY", "").strip()
        if not sk:
            # generate a temporary secret key for dev/test to avoid hard crashes
            sk = secrets.token_urlsafe(32)
            logging.warning("SECRET_KEY not set; generated temporary key (not for production)")
        self.secret_key = sk

settings = Settings()
