import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, func, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from vaaniq.server.core.database import Base


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        Index("agents_org_id_created_at_idx", "org_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    system_prompt: Mapped[str] = mapped_column(String, nullable=False, default="")
    voice_id: Mapped[str | None] = mapped_column(String, nullable=True)
    language: Mapped[str] = mapped_column(String, nullable=False, default="en")
    graph_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    graph_version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    simple_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
