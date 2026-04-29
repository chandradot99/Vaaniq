"""Add graph_version to agents

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-08

Adds graph_version integer to agents table.
Incremented every time graph_config is saved via the graph editor.
Used as part of the in-process compiled graph cache key (agent_id:version)
so publishing a new graph automatically invalidates the old cached entry.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("graph_version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("agents", "graph_version")
