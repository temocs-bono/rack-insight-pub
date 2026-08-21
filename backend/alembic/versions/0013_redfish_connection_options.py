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
    with op.batch_alter_table("rack_device_instances") as batch_op:
        batch_op.alter_column(
            "ilo_ip",
            existing_type=sa.String(length=45),
            type_=sa.String(length=255),
            existing_nullable=True,
        )

        batch_op.add_column(
            sa.Column(
                "ilo_port",
                sa.Integer(),
                nullable=False,
                server_default="443",
            )
        )

        batch_op.add_column(
            sa.Column(
                "ilo_use_https",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )

    with op.batch_alter_table("rack_device_instances") as batch_op:
        batch_op.alter_column(
            "ilo_port",
            server_default=None,
            existing_type=sa.Integer(),
            existing_nullable=False,
        )

        batch_op.alter_column(
            "ilo_use_https",
            server_default=None,
            existing_type=sa.Boolean(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("rack_device_instances") as batch_op:
        batch_op.drop_column("ilo_use_https")
        batch_op.drop_column("ilo_port")

        batch_op.alter_column(
            "ilo_ip",
            existing_type=sa.String(length=255),
            type_=sa.String(length=45),
            existing_nullable=True,
        )