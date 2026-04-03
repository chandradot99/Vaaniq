"""Create integrations table

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("config", JSONB(), nullable=False, server_default="{}"),
        sa.Column("credentials", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="connected"),
        sa.Column("meta", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name="integrations_org_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="integrations_pkey"),
    )
    op.create_index("integrations_org_id_idx", "integrations", ["org_id"])
    op.create_index("integrations_org_id_category_idx", "integrations", ["org_id", "category"])
    op.execute(
        "CREATE UNIQUE INDEX integrations_org_id_provider_uidx "
        "ON integrations (org_id, provider) WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.drop_index("integrations_org_id_provider_uidx", table_name="integrations")
    op.drop_index("integrations_org_id_category_idx", table_name="integrations")
    op.drop_index("integrations_org_id_idx", table_name="integrations")
    op.drop_table("integrations")
