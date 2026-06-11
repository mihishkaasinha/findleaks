from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Auth (required) ---
    SECRET_KEY: str
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD_HASH: str = ""

    # --- Database (required — Supabase PostgreSQL) ---
    DATABASE_URL: str

    # --- Twitter/X API (required for scanner) ---
    TWITTER_BEARER_TOKEN: str = ""

    # --- Telegram Bot (required for scanner) ---
    TELEGRAM_BOT_TOKEN: str = ""

    # --- SMTP / Email (required for alerts) ---
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""

    # --- Twilio SMS (optional) ---
    TWILIO_SID: Optional[str] = None
    TWILIO_TOKEN: Optional[str] = None
    TWILIO_NUMBER: Optional[str] = None

    # --- App Settings ---
    APP_NAME: str = "FINDLEAKS"
    FAISS_INDEX_DIR: str = "./indexes"
    UPLOAD_DIR: str = "./uploads"
    ALERT_THRESHOLD_HIGH: float = 0.80
    ALERT_THRESHOLD_REVIEW: float = 0.60
    SCAN_DEDUP_MINUTES: int = 30
    LOG_LEVEL: str = "INFO"

    # --- CORS / URLs ---
    FRONTEND_URL: str = "http://localhost:5173"
    BACKEND_URL: str = "http://localhost:8000"

    # --- Railway injects PORT automatically ---
    PORT: int = 8000

    # --- Token expiry buffer (seconds) ---
    TOKEN_EXPIRY_BUFFER: int = 100

    @field_validator("ALERT_THRESHOLD_HIGH", "ALERT_THRESHOLD_REVIEW")
    @classmethod
    def validate_threshold(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0")
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith(("postgresql://", "postgresql+asyncpg://", "postgresql+psycopg2://", "sqlite://")):
            raise ValueError(
                "DATABASE_URL must be a PostgreSQL or SQLite connection string"
            )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
