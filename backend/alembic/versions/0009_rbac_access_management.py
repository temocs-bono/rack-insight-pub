"""RBAC access management tables (1.2.1).

Revision ID: 0009
Revises: 0008

Additive: creates the RBAC tables (permissions, roles, role_permissions,
user_groups, user_group_members, role_bindings) and extends ``users`` with
display_name / email / status. Existing rows get status='ACTIVE'.

Default data (permission catalog, system roles, the Administrators group and
its binding, and migrating existing admins into that group) is seeded
idempotently at startup by ``services.rbac_service.ensure_rbac_seed`` — the same
pattern used for retention policies in 0008. This keeps the migration purely
structural and lets later releases add permissions without a new migration.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
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
        "permissions",
        *_base_columns(),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"], unique=True)

    op.create_table(
        "roles",
        *_base_columns(),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    op.create_table(
        "role_permissions",
        *_base_columns(),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"])

    op.create_table(
        "user_groups",
        *_base_columns(),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_user_groups_name", "user_groups", ["name"], unique=True)

    op.create_table(
        "user_group_members",
        *_base_columns(),
        sa.Column("user_group_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_group_id"], ["user_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_group_id", "user_id", name="uq_user_group_member"),
    )
    op.create_index(
        "ix_user_group_members_user_group_id", "user_group_members", ["user_group_id"]
    )
    op.create_index("ix_user_group_members_user_id", "user_group_members", ["user_id"])

    op.create_table(
        "role_bindings",
        *_base_columns(),
        sa.Column("user_group_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("scope_type", sa.String(16), server_default="GLOBAL", nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["user_group_id"], ["user_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_group_id", "role_id", "scope_type", "scope_id", name="uq_role_binding"
        ),
    )
    op.create_index("ix_role_bindings_user_group_id", "role_bindings", ["user_group_id"])
    op.create_index("ix_role_bindings_role_id", "role_bindings", ["role_id"])

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("display_name", sa.String(128), nullable=True))
        batch.add_column(sa.Column("email", sa.String(255), nullable=True))
        batch.add_column(
            sa.Column("status", sa.String(16), server_default="ACTIVE", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("status")
        batch.drop_column("email")
        batch.drop_column("display_name")

    op.drop_table("role_bindings")
    op.drop_table("user_group_members")
    op.drop_table("user_groups")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")
