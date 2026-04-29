"""PlatformConfig model — deployment-wide credentials managed by the platform operator.

Two separate credential stores exist; do not confuse them:

  platform_configs (this table)
    - Scope: the whole deployment (all organisations share these)
    - Who sets it: owner/admin via /v1/admin/platform-configs
    - Examples: Google OAuth app registration, Slack OAuth app, LangSmith tracing key,
                Sentry DSN, default Twilio/Deepgram/Cartesia/ElevenLabs credentials
    - Purpose: OAuth app registrations that every org uses, observability tooling,
               and default voice/telephony credentials for orgs that haven't set their own

  integrations (see models/integration.py)
    - Scope: per organisation
    - Who sets it: org members via /v1/integrations
    - Examples: org's own OpenAI key, org's Deepgram key, HubSpot access token
    - Purpose: BYOK (bring your own keys) for AI providers and third-party app connections
    - Priority: org Integration credentials ALWAYS take priority over platform_configs defaults

credentials: Fernet-encrypted JSON string — secrets (client_secret, auth_token, dsn, api_key).
config:      Plain JSONB — non-secrets returned in API responses (client_id, redirect_uri).
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from naaviq.server.core.database import Base


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
