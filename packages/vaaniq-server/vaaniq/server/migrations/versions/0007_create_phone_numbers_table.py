"""Create phone_numbers table

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-07

Links Twilio (or other telephony) numbers to agents. One number maps to one
agent; one agent may have multiple numbers (e.g. a dedicated number per language).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "phone_numbers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        # E.164 format, e.g. +14155551234  +919876543210
        sa.Column("number", sa.String(), nullable=False),
        # Telephony provider: "twilio" | "vonage" | "telnyx"
        sa.Column("provider", sa.String(), nullable=False, server_default="twilio"),
        # Provider-specific resource SID, e.g. Twilio PhoneNumberSid (PN...)
        sa.Column("sid", sa.String(), nullable=False, server_default=""),
        sa.Column("friendly_name", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_phone_numbers")),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_phone_numbers_org_id")
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.id"], name=op.f("fk_phone_numbers_agent_id")
        ),
        # Each active number is globally unique (carriers enforce this too)
        sa.UniqueConstraint("number", name=op.f("uq_phone_numbers_number")),
    )
    # Inbound call lookup: find the agent for a given Twilio number
    op.create_index("ix_phone_numbers_number", "phone_numbers", ["number"])
    # List all numbers for an org
    op.create_index("ix_phone_numbers_org_id", "phone_numbers", ["org_id"])
    # List all numbers for a specific agent
    op.create_index("ix_phone_numbers_agent_id", "phone_numbers", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_phone_numbers_agent_id", table_name="phone_numbers")
    op.drop_index("ix_phone_numbers_org_id", table_name="phone_numbers")
    op.drop_index("ix_phone_numbers_number", table_name="phone_numbers")
    op.drop_table("phone_numbers")
