from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "daily-checkin"
    environment: str = "dev"

    # Telegram
    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    webhook_secret: str | None = Field(default=None, alias="TELEGRAM_WEBHOOK_SECRET")
    public_base_url: str | None = Field(default=None, alias="PUBLIC_BASE_URL")

    # Database
    database_url: str = Field(alias="DATABASE_URL")

    # Redis / Celery
    redis_url: str = Field(alias="REDIS_URL")
    celery_broker_url: str = Field(alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(alias="CELERY_RESULT_BACKEND")

    # S3 storage (optional)
    store_media_in_s3: bool = Field(default=False, alias="STORE_MEDIA_IN_S3")
    s3_endpoint: str | None = Field(default=None, alias="S3_ENDPOINT")
    s3_bucket: str | None = Field(default=None, alias="S3_BUCKET")
    s3_access_key: str | None = Field(default=None, alias="S3_ACCESS_KEY")
    s3_secret_key: str | None = Field(default=None, alias="S3_SECRET_KEY")

    # Scheduling
    checkin_grace_hours: int = Field(default=6, alias="CHECKIN_GRACE_HOURS")
    scheduler_window_hours: int = Field(default=36, alias="SCHEDULER_WINDOW_HOURS")
    retention_days: int = Field(default=7, alias="RETENTION_DAYS")
    unreachable_recheck_hours: int = Field(default=12, alias="UNREACHABLE_RECHECK_HOURS")

    # Rate limiting
    telegram_rate_limit_per_sec: int = Field(default=25, alias="TG_RATE_LIMIT_PER_SEC")


settings = Settings()
