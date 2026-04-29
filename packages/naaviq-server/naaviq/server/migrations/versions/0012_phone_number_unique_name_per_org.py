"""Add partial unique index on (org_id, friendly_name) for active phone numbers.

Revision ID: 0012
Revises: 0011_add_voice_config_to_agents
Create Date: 2026-04-15
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE UNIQUE INDEX uq_phone_numbers_org_name_active
        ON phone_numbers (org_id, friendly_name)
        WHERE deleted_at IS NULL AND friendly_name IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_phone_numbers_org_name_active")
