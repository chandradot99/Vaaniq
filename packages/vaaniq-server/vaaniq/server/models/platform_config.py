"""PlatformConfig model — platform-level credentials for OAuth apps and external services.

Unlike the integrations table (per-org credentials), these are credentials owned
by the platform operator — e.g. the Google OAuth app client_id/secret registered
for this deployment, LangSmith API key, Sentry DSN.

credentials: Fernet-encrypted JSON string — secrets (client_secret, api_key, dsn).
config:      Plain JSONB — non-secrets returned in API responses (client_id, redirect_uri).
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from vaaniq.server.core.database import Base


class PlatformConfig(Base):
    __tablename__ = "platform_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    provider: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    credentials: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
