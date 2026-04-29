"""
0011 — Add voice_config JSONB column to agents table.

Stores agent-level STT/TTS defaults (provider, model, voice, language, speed).
These are overridden per-phone-number by the existing phone_numbers.voice_config.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("voice_config", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "voice_config")
