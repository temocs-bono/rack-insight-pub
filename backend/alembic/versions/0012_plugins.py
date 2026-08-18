"""Plugin registry table (Plugin Architecture Foundation).

Revision ID: 0012
Revises: 0011

Additive only: one new ``plugins`` table. No existing table is modified.
Configuration (endpoint/enabled) and observed runtime state (status,
last_health_check, …) live on the same row but are managed separately by the
registry seeder and the health monitor.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "plugins",
        *_base_columns(),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.String(32), nullable=True),
        sa.Column("api_version", sa.String(16), nullable=False),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("managed_by_config", sa.Boolean(), nullable=False),
        sa.Column("manifest", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("last_health_check", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_plugins_name", "plugins", ["name"], unique=True)
    op.create_index("ix_plugins_status", "plugins", ["status"])


def downgrade() -> None:
    op.drop_index("ix_plugins_status", table_name="plugins")
    op.drop_index("ix_plugins_name", table_name="plugins")
    op.drop_table("plugins")
