"""Collector failure diagnosis: categorized error columns on collector_runs.

Revision ID: 0003
Revises: 0002
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "collector_runs", sa.Column("error_code", sa.String(64), nullable=True)
    )
    op.add_column(
        "collector_runs", sa.Column("readable_message", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("collector_runs", "readable_message")
    op.drop_column("collector_runs", "error_code")
