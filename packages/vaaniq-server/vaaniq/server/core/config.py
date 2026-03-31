from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://vaaniq:vaaniq@localhost:5432/vaaniq"
    database_replica_url: Optional[str] = None
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-production"
    fernet_key: str = ""
    allowed_origins: str = "http://localhost:3000"
    storage_backend: str = "minio"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "vaaniq"
    sentry_dsn: Optional[str] = None
    otel_exporter_otlp_endpoint: Optional[str] = None
    environment: str = "development"
    backend_url: str = "http://localhost:8000"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()
