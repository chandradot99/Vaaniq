"""Create api_keys table

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("service", sa.String(), nullable=False),
        sa.Column("encrypted_key", sa.String(), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name="api_keys_org_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="api_keys_pkey"),
    )
    op.create_index("api_keys_org_id_idx", "api_keys", ["org_id"])
    # Partial unique index — allows delete + re-add of the same service
    op.execute(
        "CREATE UNIQUE INDEX api_keys_org_id_service_uidx "
        "ON api_keys (org_id, service) WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.drop_index("api_keys_org_id_service_uidx", table_name="api_keys")
    op.drop_index("api_keys_org_id_idx", table_name="api_keys")
    op.drop_table("api_keys")
