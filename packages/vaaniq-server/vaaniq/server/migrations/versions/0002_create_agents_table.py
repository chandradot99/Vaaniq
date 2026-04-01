"""Create agents table

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-01
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("system_prompt", sa.String(), nullable=False, server_default=""),
        sa.Column("voice_id", sa.String(), nullable=True),
        sa.Column("language", sa.String(), nullable=False, server_default="en"),
        sa.Column("graph_config", JSONB(), nullable=True),
        sa.Column("simple_mode", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name="agents_org_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="agents_pkey"),
    )
    op.create_index("agents_org_id_idx", "agents", ["org_id"])
    op.create_index("agents_org_id_created_at_idx", "agents", ["org_id", "created_at"])


def downgrade() -> None:
    op.drop_index("agents_org_id_created_at_idx", table_name="agents")
    op.drop_index("agents_org_id_idx", table_name="agents")
    op.drop_table("agents")
