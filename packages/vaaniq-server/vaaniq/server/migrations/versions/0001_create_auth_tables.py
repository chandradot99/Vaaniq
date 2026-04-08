"""Create auth tables

Revision ID: 0001
Revises:
Create Date: 2026-04-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="users_pkey"),
    )
    op.create_index("users_email_idx", "users", ["email"], unique=True)

    op.create_table(
        "organizations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("plan", sa.String(), nullable=False, server_default="free"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="organizations_owner_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="organizations_pkey"),
    )

    op.create_table(
        "org_members",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name="org_members_org_id_fkey"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="org_members_user_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="org_members_pkey"),
        sa.UniqueConstraint("org_id", "user_id", name="org_members_org_id_user_id_key"),
    )
    op.create_index("org_members_user_id_idx", "org_members", ["user_id"])

    op.create_table(
        "user_identities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),      # 'email' | 'google' | 'github'
        sa.Column("provider_user_id", sa.String(), nullable=True),  # null for email/password
        sa.Column("password_hash", sa.String(), nullable=True),     # null for OAuth providers
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="user_identities_user_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="user_identities_pkey"),
        sa.UniqueConstraint("provider", "provider_user_id", name="user_identities_provider_provider_user_id_key"),
    )
    op.create_index("user_identities_user_id_idx", "user_identities", ["user_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),   # sha256(token), never raw
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),  # null = active
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="refresh_tokens_user_id_fkey"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name="refresh_tokens_org_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="refresh_tokens_pkey"),
    )
    op.create_index("refresh_tokens_token_hash_idx", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("refresh_tokens_user_id_idx", "refresh_tokens", ["user_id"])

    op.create_table(
        "invitations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="member"),
        sa.Column("token_hash", sa.String(), nullable=False),   # sha256(token)
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name="invitations_org_id_fkey"),
        sa.ForeignKeyConstraint(["invited_by_id"], ["users.id"], name="invitations_invited_by_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="invitations_pkey"),
    )
    op.create_index("invitations_token_hash_idx", "invitations", ["token_hash"], unique=True)
    op.create_index("invitations_org_id_email_idx", "invitations", ["org_id", "email"])


def downgrade() -> None:
    op.drop_table("invitations")
    op.drop_table("refresh_tokens")
    op.drop_table("user_identities")
    op.drop_table("org_members")
    op.drop_table("organizations")
    op.drop_table("users")
