"""Sensor thresholds from Redfish (upper/lower) on sensors.

Revision ID: 0004
Revises: 0003
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sensors", sa.Column("upper_threshold", sa.String(64), nullable=True))
    op.add_column("sensors", sa.Column("lower_threshold", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("sensors", "lower_threshold")
    op.drop_column("sensors", "upper_threshold")
