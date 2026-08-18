"""Discovery cache and retention policies (1.2.0).

Revision ID: 0008
Revises: 0007

Additive only: two new tables. No existing table is modified.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
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
        "discovered_devices",
        *_base_columns(),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("sysname", sa.String(255), nullable=True),
        sa.Column("sysdescr", sa.Text(), nullable=True),
        sa.Column("sysobjectid", sa.String(255), nullable=True),
        sa.Column("vendor", sa.String(128), nullable=True),
        sa.Column("device_type_guess", sa.String(32), nullable=True),
        sa.Column("serial", sa.String(128), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "IMPORTED", "IGNORED", name="discovery_status"),
            nullable=False,
        ),
        sa.Column("imported_device_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_discovered_devices_ip_address", "discovered_devices", ["ip_address"]
    )

    op.create_table(
        "retention_policies",
        *_base_columns(),
        sa.Column("category", sa.String(64), nullable=False, unique=True),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("retention_policies")
    op.drop_index("ix_discovered_devices_ip_address", table_name="discovered_devices")
    op.drop_table("discovered_devices")
    sa.Enum(name="discovery_status").drop(op.get_bind(), checkfirst=True)
