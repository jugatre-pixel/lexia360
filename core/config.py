import os

class Settings:
    app_name: str = "Lexia360"
    app_version: str = os.getenv("APP_VERSION", "lexia360-sprint1-modular-alembic")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    database_url: str = os.getenv("DATABASE_URL", "").strip()
    secret_key: str = os.getenv("SECRET_KEY", "").strip()

    def __init__(self):
        if not self.database_url:
            raise RuntimeError("❌ Falta DATABASE_URL (Render -> Environment Variables)")
        if self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql+psycopg2://", 1)
        if not self.secret_key:
            raise RuntimeError("❌ Falta SECRET_KEY (Render -> Environment Variables)")

settings = Settings()

