"""add redfish connection options

Revision ID: 0013
Revises: 0012
"""

from alembic import op
import sqlalchemy as sa


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "rack_device_instances",
        "ilo_ip",
        existing_type=sa.String(length=45),
        type_=sa.String(length=255),
        existing_nullable=True,
    )

    op.add_column(
        "rack_device_instances",
        sa.Column(
            "ilo_port",
            sa.Integer(),
            nullable=False,
            server_default="443",
        ),
    )

    op.add_column(
        "rack_device_instances",
        sa.Column(
            "ilo_use_https",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    op.alter_column(
        "rack_device_instances",
        "ilo_port",
        server_default=None,
    )

    op.alter_column(
        "rack_device_instances",
        "ilo_use_https",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("rack_device_instances", "ilo_use_https")
    op.drop_column("rack_device_instances", "ilo_port")

    op.alter_column(
        "rack_device_instances",
        "ilo_ip",
        existing_type=sa.String(length=255),
        type_=sa.String(length=45),
        existing_nullable=True,
    )