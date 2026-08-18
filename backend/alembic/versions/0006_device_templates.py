"""Split Device into DeviceTemplate + Rack Device Instance.

Revision ID: 0006
Revises: 0005

The existing ``devices`` table holds deployment data (hostname, IPs,
credentials, rack, status) — i.e. installed instances — so it is renamed to
``rack_device_instances``. Its foreign keys (snapshots.device_id,
rack_units.device_id, collector_runs.device_id) follow the rename with no
value rewrites, so existing rack layouts, snapshots and exports stay valid.

A new ``device_templates`` table holds the shared hardware model. Existing
instances are grouped by (vendor, model) into one template each (dedup), and
linked via the new ``rack_device_instances.template_id`` column. No data loss:
every original device becomes exactly one instance plus a shared template.
"""
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0006"
down_revision: str | None = "0005"
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
    op.rename_table("devices", "rack_device_instances")

    op.create_table(
        "device_templates",
        *_base_columns(),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("vendor", sa.String(128), nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("cpu", sa.String(255), nullable=True),
        sa.Column("memory", sa.String(255), nullable=True),
        sa.Column("storage", sa.String(255), nullable=True),
        sa.Column("firmware", sa.String(255), nullable=True),
        sa.Column("nic", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
    )

    with op.batch_alter_table("rack_device_instances") as batch_op:
        batch_op.add_column(sa.Column("template_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("asset_tag", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("serial_override", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("description", sa.String(512), nullable=True))
        batch_op.create_foreign_key(
            "fk_instance_template",
            "device_templates",
            ["template_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if context.is_offline_mode():
        # No connection to backfill; existing offline deployments run online.
        return

    _backfill_templates()


def _backfill_templates() -> None:
    bind = op.get_bind()
    templates = sa.table(
        "device_templates",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("vendor", sa.String()),
        sa.column("model", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    instances = sa.table(
        "rack_device_instances",
        sa.column("id", sa.Uuid()),
        sa.column("vendor", sa.String()),
        sa.column("model", sa.String()),
        sa.column("template_id", sa.Uuid()),
    )

    groups = bind.execute(
        sa.select(instances.c.vendor, instances.c.model).distinct()
    ).all()

    used_names: set[str] = set()
    for vendor, model in groups:
        base_name = " ".join(part for part in (vendor, model) if part).strip()
        if not base_name:
            base_name = "Unspecified Hardware"
        name = base_name
        suffix = 2
        while name in used_names:
            name = f"{base_name} ({suffix})"
            suffix += 1
        used_names.add(name)

        template_id = uuid.uuid4()
        bind.execute(
            templates.insert().values(
                id=template_id,
                name=name,
                vendor=vendor,
                model=model,
                created_at=sa.func.now(),
                updated_at=sa.func.now(),
            )
        )

        condition = instances.c.template_id.is_(None)
        condition &= (
            instances.c.vendor.is_(None) if vendor is None
            else instances.c.vendor == vendor
        )
        condition &= (
            instances.c.model.is_(None) if model is None
            else instances.c.model == model
        )
        bind.execute(instances.update().where(condition).values(template_id=template_id))


def downgrade() -> None:
    with op.batch_alter_table("rack_device_instances") as batch_op:
        batch_op.drop_constraint("fk_instance_template", type_="foreignkey")
        batch_op.drop_column("description")
        batch_op.drop_column("serial_override")
        batch_op.drop_column("asset_tag")
        batch_op.drop_column("template_id")
    op.drop_table("device_templates")
    op.rename_table("rack_device_instances", "devices")
