"""Session model — one row per agent conversation across all channels."""
from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey, Enum, func
)
from sqlalchemy.dialects.postgresql import JSONB
import enum

from vaaniq.server.core.database import Base


class ChannelEnum(str, enum.Enum):
    chat = "chat"
    voice = "voice"
    whatsapp = "whatsapp"
    sms = "sms"
    telegram = "telegram"


class SessionStatus(str, enum.Enum):
    active = "active"
    ended = "ended"


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    org_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False, index=True)
    channel = Column(Enum(ChannelEnum), nullable=False, default=ChannelEnum.chat)
    user_id = Column(String, nullable=False, default="")
    status = Column(Enum(SessionStatus), nullable=False, default=SessionStatus.active)

    # Conversation data
    transcript = Column(JSONB, nullable=False, default=list)   # list of Message dicts
    tool_calls = Column(JSONB, nullable=False, default=list)   # list of ToolCall dicts

    # Post-session analysis
    duration_seconds = Column(Integer, nullable=True)
    sentiment = Column(String, nullable=True)
    summary = Column(String, nullable=True)

    # Flexible metadata (e.g. voice: phone number; whatsapp: wa_id)
    meta = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
