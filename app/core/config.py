import os

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://family:family123@localhost:5432/family_mission"
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    upload_dir: str = "uploads"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    platform_admin_email: str = "admin@familymission.local"
    platform_admin_password: str = "admin123456"
    platform_admin_name: str = "Super Admin"
    platform_admin_path: str = "/admin"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    environment: str = "development"
    rate_limit_auth_per_minute: int = 10
    rate_limit_global_per_minute: int = 100
    rate_limit_forgot_password_per_minute: int = 3
    rate_limit_invite_per_hour: int = 10
    max_upload_bytes: int = 2 * 1024 * 1024
    frontend_base_url: str = "http://localhost:5173"
    backend_base_url: str = "http://localhost:8000"
    email_token_expire_hours: int = 24
    reset_token_expire_minutes: int = 45
    redemption_mode: str = "symbolic"
    legal_doc_version: str = "1.0"
    redis_url: str = ""
    sentry_dsn: str = ""

    payment_qris_image_url: str = ""
    payment_bank_name: str = ""
    payment_bank_account: str = ""
    payment_bank_holder: str = ""
    payment_instructions_text: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        if os.getenv("ENVIRONMENT", "development").lower() in ("production", "prod"):
            if value == "dev-secret-key-change-in-production" or len(value) < 32:
                raise ValueError("SECRET_KEY must be set to a strong value in production")
        return value

    class Config:
        env_file = ".env"


settings = Settings()
