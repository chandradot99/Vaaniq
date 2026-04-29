"""Create sessions table

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False, server_default="chat"),
        sa.Column("user_id", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("transcript", JSONB(), nullable=False, server_default="[]"),
        sa.Column("tool_calls", JSONB(), nullable=False, server_default="[]"),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("sentiment", sa.String(), nullable=True),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("meta", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name=op.f("fk_sessions_org_id")),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], name=op.f("fk_sessions_agent_id")),
    )
    op.create_index("ix_sessions_org_id_created_at", "sessions", ["org_id", "created_at"])
    op.create_index("ix_sessions_agent_id_created_at", "sessions", ["agent_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_sessions_agent_id_created_at", table_name="sessions")
    op.drop_index("ix_sessions_org_id_created_at", table_name="sessions")
    op.drop_table("sessions")
