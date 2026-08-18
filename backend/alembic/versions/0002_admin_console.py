"""Admin console: clusters.site, credentials, collector_runs, device fields.

Revision ID: 0002
Revises: 0001

Adds the columns/tables introduced by the Admin Console feature:
- ALTER TABLE clusters ADD COLUMN site VARCHAR(255)
- credentials table (named Redfish/SSH/SNMP credentials)
- collector_runs table (collection audit log)
- devices: orientation, collector_types, credential references

Every step is guarded by an existence check. This migration adopts databases
that ran the pre-Alembic create_all startup, which created the NEW TABLES
(credentials, collector_runs) but silently skipped the NEW COLUMNS on
existing tables (clusters.site, devices.*). Blindly re-creating those tables
crashed such deployments with DuplicateTable on startup.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if context.is_offline_mode():
        # --sql mode has no live connection to inspect; emit the full DDL.
        existing_tables: set[str] = set()
        cluster_columns: set[str] = set()
        device_columns: set[str] = set()
    else:
        inspector = sa.inspect(op.get_bind())
        existing_tables = set(inspector.get_table_names())
        cluster_columns = {c["name"] for c in inspector.get_columns("clusters")}
        device_columns = {c["name"] for c in inspector.get_columns("devices")}

    # -- clusters ------------------------------------------------------------
    # ALTER TABLE clusters ADD COLUMN site VARCHAR(255);
    if "site" not in cluster_columns:
        op.add_column("clusters", sa.Column("site", sa.String(255), nullable=True))

    # -- credentials ----------------------------------------------------------
    _create_credentials_table(existing_tables)

    # -- collector_runs -------------------------------------------------------
    _create_collector_runs_table(existing_tables)

    # -- devices --------------------------------------------------------------
    _add_device_columns(device_columns)


def _create_credentials_table(existing_tables: set[str]) -> None:
    if "credentials" in existing_tables:
        return
    op.create_table(
        "credentials",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column(
            "credential_type",
            sa.Enum("REDFISH", "SSH", "SNMP", name="credential_type"),
            nullable=False,
        ),
        sa.Column("username", sa.String(128), nullable=True),
        sa.Column("password_encrypted", sa.String(512), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
    )


def _create_collector_runs_table(existing_tables: set[str]) -> None:
    if "collector_runs" in existing_tables:
        return
    op.create_table(
        "collector_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("trigger", sa.Text(), nullable=True),
    )
    op.create_index("ix_collector_runs_device_id", "collector_runs", ["device_id"])


def _add_device_columns(device_columns: set[str]) -> None:
    credential_fk_columns = (
        ("redfish_credential_id", "fk_devices_redfish_credential"),
        ("ssh_credential_id", "fk_devices_ssh_credential"),
        ("snmp_credential_id", "fk_devices_snmp_credential"),
    )
    missing_fk_columns = [
        (column, constraint)
        for column, constraint in credential_fk_columns
        if column not in device_columns
    ]
    needs_orientation = "orientation" not in device_columns
    needs_collector_types = "collector_types" not in device_columns
    if not (needs_orientation or needs_collector_types or missing_fk_columns):
        return

    device_orientation = sa.Enum("FRONT", "REAR", name="device_orientation")
    if needs_orientation:
        device_orientation.create(op.get_bind(), checkfirst=True)

    # batch_alter_table executes plain ALTERs on PostgreSQL and falls back to
    # copy-and-move on SQLite (which cannot ALTER-add FK constraints).
    with op.batch_alter_table("devices") as batch_op:
        if needs_orientation:
            batch_op.add_column(
                sa.Column(
                    "orientation",
                    device_orientation,
                    nullable=False,
                    server_default="FRONT",
                )
            )
        if needs_collector_types:
            batch_op.add_column(
                sa.Column("collector_types", sa.String(64), nullable=True)
            )
        for column, _constraint in missing_fk_columns:
            batch_op.add_column(sa.Column(column, sa.Uuid(), nullable=True))
        for column, constraint in missing_fk_columns:
            batch_op.create_foreign_key(
                constraint, "credentials", [column], ["id"], ondelete="SET NULL"
            )


def downgrade() -> None:
    with op.batch_alter_table("devices") as batch_op:
        batch_op.drop_constraint("fk_devices_snmp_credential", type_="foreignkey")
        batch_op.drop_constraint("fk_devices_ssh_credential", type_="foreignkey")
        batch_op.drop_constraint("fk_devices_redfish_credential", type_="foreignkey")
        batch_op.drop_column("snmp_credential_id")
        batch_op.drop_column("ssh_credential_id")
        batch_op.drop_column("redfish_credential_id")
        batch_op.drop_column("collector_types")
        batch_op.drop_column("orientation")
    sa.Enum(name="device_orientation").drop(op.get_bind(), checkfirst=True)
    op.drop_table("collector_runs")
    op.drop_table("credentials")
    sa.Enum(name="credential_type").drop(op.get_bind(), checkfirst=True)
    op.drop_column("clusters", "site")
