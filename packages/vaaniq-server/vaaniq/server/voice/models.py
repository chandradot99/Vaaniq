"""
SQLAlchemy model for phone_numbers table.

Links a telephony number (Twilio, Vonage, Telnyx) to an agent within an org.
Inbound calls arrive at a number → look up the agent → route to its graph.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from vaaniq.server.core.database import Base


class PhoneNumber(Base):
    __tablename__ = "phone_numbers"
    __table_args__ = (
        UniqueConstraint("number", name="uq_phone_numbers_number"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agents.id"), nullable=False)
    # E.164 format — e.g. +14155551234, +919876543210
    number: Mapped[str] = mapped_column(String, nullable=False)
    # Telephony provider: "twilio" | "vonage" | "telnyx"
    provider: Mapped[str] = mapped_column(String, nullable=False, server_default="twilio")
    # Provider-specific resource SID, e.g. Twilio PhoneNumberSid (PN...)
    sid: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    friendly_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # Per-pipeline voice config: STT/TTS provider, model, voice ID, language overrides.
    # Null = auto-resolve from org integrations / platform defaults.
    voice_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<PhoneNumber {self.number} agent={self.agent_id}>"
