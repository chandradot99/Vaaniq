"""Create session_events table

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-04
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "session_events",
        sa.Column("id",          sa.String(),                     nullable=False),
        sa.Column("session_id",  sa.String(),                     nullable=False),
        sa.Column("turn",        sa.SmallInteger(),               nullable=False),
        sa.Column("seq",         sa.SmallInteger(),               nullable=False),
        sa.Column("event_type",  sa.String(),                     nullable=False),
        sa.Column("name",        sa.String(),                     nullable=False, server_default=""),
        sa.Column("started_at",  sa.DateTime(timezone=True),      nullable=False),
        sa.Column("ended_at",    sa.DateTime(timezone=True),      nullable=True),
        sa.Column("duration_ms", sa.Integer(),                    nullable=True),
        sa.Column("status",      sa.String(),                     nullable=False, server_default="success"),
        sa.Column("data",        JSONB(),                         nullable=False, server_default="{}"),
        sa.Column("error",       sa.Text(),                       nullable=True),
        sa.Column("created_at",  sa.DateTime(timezone=True),      nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_events")),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name=op.f("fk_session_events_session_id")),
    )
    # Primary query pattern: fetch all events for a session ordered for timeline rendering
    op.create_index("ix_session_events_session_turn_seq", "session_events", ["session_id", "turn", "seq"])
    # Secondary: filter by event type within a session (e.g. all LLM calls)
    op.create_index("ix_session_events_session_type",    "session_events", ["session_id", "event_type"])


def downgrade() -> None:
    op.drop_index("ix_session_events_session_type",    table_name="session_events")
    op.drop_index("ix_session_events_session_turn_seq", table_name="session_events")
    op.drop_table("session_events")
