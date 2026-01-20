import os
from functools import lru_cache


class Settings:
    # =========================
    # APP
    # =========================
    APP_NAME: str = "Lexia360"
    APP_VERSION: str = os.getenv("APP_VERSION", "lexia360-v16-documents-checklist")
    ENV: str = os.getenv("ENV", "production")

    # =========================
    # DATABASE
    # =========================
    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()
    if not DATABASE_URL:
        raise RuntimeError("❌ DATABASE_URL no definida")

    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgres://", "postgresql+psycopg2://", 1
        )
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgresql://", "postgresql+psycopg2://", 1
        )

    # =========================
    # SECURITY
    # =========================
    SECRET_KEY: str = os.getenv("SECRET_KEY", "").strip()
    if not SECRET_KEY or len(SECRET_KEY) < 32:
        raise RuntimeError("❌ SECRET_KEY inválida o demasiado corta")

    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    )

    # =========================
    # CORS
    # =========================
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")

    @property
    def allowed_origins(self):
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
