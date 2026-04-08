"""Add voice_config to phone_numbers

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-07

Adds a voice_config JSONB column to phone_numbers table.
Stores per-pipeline STT/TTS provider, model, voice ID, and language overrides.
Null means "auto-resolve from org integrations / platform defaults".

A phone number IS the voice pipeline: it owns the connection between
a telephony number, an agent, and the voice settings for that call path.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "phone_numbers",
        sa.Column("voice_config", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("phone_numbers", "voice_config")
