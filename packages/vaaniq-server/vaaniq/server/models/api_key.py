import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from vaaniq.server.core.database import Base


class ApiKey(Base):
    """Encrypted BYOK key per service per org.

    Shared model — lives in models/ because sessions and voice will import
    this directly to build the org_keys dict at runtime.
    """
    __tablename__ = "api_keys"
    __table_args__ = (
        # Partial unique index: allows delete + re-add of the same service
        Index(
            "api_keys_org_id_service_uidx",
            "org_id", "service",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        Index("api_keys_org_id_idx", "org_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), nullable=False)
    service: Mapped[str] = mapped_column(String, nullable=False)
    encrypted_key: Mapped[str] = mapped_column(String, nullable=False)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
