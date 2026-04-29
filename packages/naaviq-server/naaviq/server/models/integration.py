import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from naaviq.server.core.database import Base


class Integration(Base):
    """Unified credentials store for all external services per org.

    Covers LLM providers (openai, anthropic), voice services (deepgram,
    elevenlabs), third-party apps (google, hubspot), and infrastructure
    connectors (pinecone, redis).

    categories:
        llm            — OpenAI, Anthropic, Gemini, Groq, Azure OpenAI
        stt            — Deepgram, AssemblyAI, Sarvam
        tts            — ElevenLabs, Cartesia
        telephony      — Twilio, Vonage, Telnyx
        app            — Google, HubSpot, Salesforce, Slack
        infrastructure — Pinecone, Qdrant, Redis, PostgreSQL

    credentials: Fernet-encrypted JSON string — never returned to clients.
    config: Non-secret JSONB — returned in API responses.
    meta: Arbitrary metadata (connected account email, last_used_at, etc.).
    """
    __tablename__ = "integrations"
    __table_args__ = (
        Index(
            "integrations_org_id_provider_uidx",
            "org_id", "provider",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        Index("integrations_org_id_idx", "org_id"),
        Index("integrations_org_id_category_idx", "org_id", "category"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    credentials: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="connected")
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
