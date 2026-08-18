"""Initial schema (pre-admin-console baseline).

Revision ID: 0001
Revises:
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    """id / created_at / updated_at required on every table."""
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        *_base_columns(),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("ADMIN", "USER", name="user_role"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "clusters",
        *_base_columns(),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("vendor", sa.String(128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
    )

    op.create_table(
        "racks",
        *_base_columns(),
        sa.Column(
            "cluster_id",
            sa.Uuid(),
            sa.ForeignKey("clusters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )

    op.create_table(
        "devices",
        *_base_columns(),
        sa.Column(
            "rack_id",
            sa.Uuid(),
            sa.ForeignKey("racks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column(
            "device_type",
            sa.Enum("SERVER", "SWITCH", "PDU", "KVM", "OTHER", name="device_type"),
            nullable=False,
        ),
        sa.Column("vendor", sa.String(128), nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("management_ip", sa.String(45), nullable=True),
        sa.Column("ilo_ip", sa.String(45), nullable=True),
        sa.Column("ilo_username", sa.String(128), nullable=True),
        sa.Column("ilo_password_encrypted", sa.String(512), nullable=True),
        sa.Column("ssh_username", sa.String(128), nullable=True),
        sa.Column("ssh_password_encrypted", sa.String(512), nullable=True),
        sa.Column("snmp_community_encrypted", sa.String(512), nullable=True),
        sa.Column(
            "status",
            sa.Enum("ONLINE", "OFFLINE", "WARNING", "UNKNOWN", name="device_status"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_devices_hostname", "devices", ["hostname"])

    op.create_table(
        "rack_units",
        *_base_columns(),
        sa.Column(
            "rack_id",
            sa.Uuid(),
            sa.ForeignKey("racks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("u_position", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("rack_id", "u_position", name="uq_rack_u_position"),
    )

    op.create_table(
        "snapshots",
        *_base_columns(),
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("collector_version", sa.String(32), nullable=False),
        sa.Column("redfish_success", sa.Boolean(), nullable=False),
        sa.Column("ssh_success", sa.Boolean(), nullable=False),
        sa.Column("virsh_success", sa.Boolean(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
    )
    op.create_index("ix_snapshots_device_id", "snapshots", ["device_id"])

    def snapshot_fk() -> sa.Column:
        return sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("snapshots.id", ondelete="CASCADE"),
            nullable=False,
        )

    op.create_table(
        "cpus",
        *_base_columns(),
        snapshot_fk(),
        sa.Column("socket", sa.String(64), nullable=True),
        sa.Column("vendor", sa.String(128), nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("cores", sa.Integer(), nullable=True),
        sa.Column("threads", sa.Integer(), nullable=True),
        sa.Column("frequency", sa.String(64), nullable=True),
        sa.Column("cache", sa.String(128), nullable=True),
        sa.Column("microcode", sa.String(64), nullable=True),
        sa.Column("serial", sa.String(128), nullable=True),
    )
    op.create_index("ix_cpus_snapshot_id", "cpus", ["snapshot_id"])

    op.create_table(
        "memories",
        *_base_columns(),
        snapshot_fk(),
        sa.Column("slot", sa.String(64), nullable=True),
        sa.Column("vendor", sa.String(128), nullable=True),
        sa.Column("part_number", sa.String(128), nullable=True),
        sa.Column("serial", sa.String(128), nullable=True),
        sa.Column("capacity_gb", sa.Integer(), nullable=True),
        sa.Column("speed", sa.String(64), nullable=True),
        sa.Column("type", sa.String(64), nullable=True),
        sa.Column("ecc", sa.Boolean(), nullable=True),
        sa.Column("status", sa.String(64), nullable=True),
    )
    op.create_index("ix_memories_snapshot_id", "memories", ["snapshot_id"])

    op.create_table(
        "nics",
        *_base_columns(),
        snapshot_fk(),
        sa.Column("name", sa.String(128), nullable=True),
        sa.Column("vendor", sa.String(128), nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("mac", sa.String(32), nullable=True),
        sa.Column("firmware", sa.String(128), nullable=True),
        sa.Column("driver", sa.String(128), nullable=True),
        sa.Column("speed", sa.String(64), nullable=True),
        sa.Column("pci_slot", sa.String(64), nullable=True),
        sa.Column("serial", sa.String(128), nullable=True),
        sa.Column("link_status", sa.String(32), nullable=True),
    )
    op.create_index("ix_nics_snapshot_id", "nics", ["snapshot_id"])

    op.create_table(
        "firmwares",
        *_base_columns(),
        snapshot_fk(),
        sa.Column("component", sa.String(255), nullable=True),
        sa.Column("version", sa.String(128), nullable=True),
        sa.Column("release_date", sa.String(64), nullable=True),
        sa.Column("health", sa.String(32), nullable=True),
    )
    op.create_index("ix_firmwares_snapshot_id", "firmwares", ["snapshot_id"])

    op.create_table(
        "storages",
        *_base_columns(),
        snapshot_fk(),
        sa.Column("controller", sa.String(255), nullable=True),
        sa.Column("raid_level", sa.String(64), nullable=True),
        sa.Column("vendor", sa.String(128), nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("serial", sa.String(128), nullable=True),
        sa.Column("capacity", sa.String(64), nullable=True),
        sa.Column("firmware", sa.String(128), nullable=True),
        sa.Column("health", sa.String(32), nullable=True),
    )
    op.create_index("ix_storages_snapshot_id", "storages", ["snapshot_id"])

    op.create_table(
        "disks",
        *_base_columns(),
        sa.Column(
            "storage_id",
            sa.Uuid(),
            sa.ForeignKey("storages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slot", sa.String(64), nullable=True),
        sa.Column("vendor", sa.String(128), nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("serial", sa.String(128), nullable=True),
        sa.Column("capacity", sa.String(64), nullable=True),
        sa.Column("firmware", sa.String(128), nullable=True),
        sa.Column("health", sa.String(32), nullable=True),
    )

    op.create_table(
        "networks",
        *_base_columns(),
        snapshot_fk(),
        sa.Column("interface", sa.String(128), nullable=True),
        sa.Column("ipv4", sa.String(64), nullable=True),
        sa.Column("ipv6", sa.String(128), nullable=True),
        sa.Column("gateway", sa.String(64), nullable=True),
        sa.Column("dns", sa.String(255), nullable=True),
        sa.Column("vlan", sa.String(32), nullable=True),
        sa.Column("bond", sa.String(64), nullable=True),
        sa.Column("mtu", sa.Integer(), nullable=True),
        sa.Column("speed", sa.String(64), nullable=True),
        sa.Column("duplex", sa.String(32), nullable=True),
        sa.Column("mac", sa.String(32), nullable=True),
    )
    op.create_index("ix_networks_snapshot_id", "networks", ["snapshot_id"])

    op.create_table(
        "vms",
        *_base_columns(),
        snapshot_fk(),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("uuid", sa.String(64), nullable=True),
        sa.Column("state", sa.String(64), nullable=True),
        sa.Column("vcpu", sa.Integer(), nullable=True),
        sa.Column("memory", sa.String(64), nullable=True),
        sa.Column("os", sa.String(255), nullable=True),
        sa.Column("kernel", sa.String(128), nullable=True),
        sa.Column("ip", sa.String(255), nullable=True),
    )
    op.create_index("ix_vms_snapshot_id", "vms", ["snapshot_id"])

    op.create_table(
        "sensors",
        *_base_columns(),
        snapshot_fk(),
        sa.Column("type", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("value", sa.String(64), nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
    )
    op.create_index("ix_sensors_snapshot_id", "sensors", ["snapshot_id"])

    op.create_table(
        "switch_inventories",
        *_base_columns(),
        snapshot_fk(),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("ios_version", sa.String(128), nullable=True),
        sa.Column("serial", sa.String(128), nullable=True),
        sa.Column("uptime", sa.String(128), nullable=True),
    )
    op.create_index(
        "ix_switch_inventories_snapshot_id", "switch_inventories", ["snapshot_id"]
    )


def downgrade() -> None:
    for table in (
        "switch_inventories",
        "sensors",
        "vms",
        "networks",
        "disks",
        "storages",
        "firmwares",
        "nics",
        "memories",
        "cpus",
        "snapshots",
        "rack_units",
        "devices",
        "racks",
        "clusters",
        "users",
    ):
        op.drop_table(table)
    for enum_name in ("device_status", "device_type", "user_role"):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
