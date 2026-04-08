"""
0010 — Replace global unique constraint on phone_numbers.number with a partial
       unique index that only covers active (non-deleted) rows.

The original constraint (uq_phone_numbers_number) applied to ALL rows including
soft-deleted ones, which prevented re-adding a number after deletion.

The new partial index enforces uniqueness only where deleted_at IS NULL, so:
  - Two active rows cannot share a number              ← still enforced
  - A deleted row does not block re-adding the number  ← now allowed
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old blanket unique constraint
    op.drop_constraint("uq_phone_numbers_number", "phone_numbers", type_="unique")

    # Add a partial unique index — only active rows count
    op.execute(
        """
        CREATE UNIQUE INDEX uq_phone_numbers_number_active
        ON phone_numbers (number)
        WHERE deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_phone_numbers_number_active")
    op.create_unique_constraint("uq_phone_numbers_number", "phone_numbers", ["number"])
