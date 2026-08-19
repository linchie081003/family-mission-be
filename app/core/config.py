import os

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://family:family123@localhost:5432/family_mission"
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours (OWASP: shorter than 7 days)
    upload_dir: str = "uploads"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    platform_admin_email: str = "admin@familymission.local"
    platform_admin_password: str = "admin123456"
    platform_admin_name: str = "Super Admin"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    environment: str = "development"
    rate_limit_auth_per_minute: int = 10
    max_upload_bytes: int = 2 * 1024 * 1024

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
