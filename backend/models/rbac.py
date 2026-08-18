"""RBAC models (1.2.1 Access Management).

Authorization flow:

    User -> User Group -> Role Binding -> Role -> Permissions

Users never receive permissions directly. They are members of one or more
User Groups; each User Group is granted Roles through Role Bindings; each Role
carries a set of Permissions (business-action codes). The effective permission
set of a user is the union of all permissions reachable through this chain.

Role Bindings carry a ``scope_type`` (GLOBAL today) that is schema-compatible
with future CLUSTER / RACK scoping via the nullable ``scope_id`` column.
"""
import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import TimestampedModel

# Role binding scope types. Only GLOBAL is honoured by the resolver today; the
# column exists so CLUSTER / RACK scoping can be added without a schema change.
SCOPE_GLOBAL = "GLOBAL"
SCOPE_CLUSTER = "CLUSTER"
SCOPE_RACK = "RACK"


class Permission(TimestampedModel):
    """A single business-action code (e.g. ``cluster.create``)."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Role(TimestampedModel):
    """A named bundle of permissions. System roles cannot be edited/deleted."""

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(default=False, nullable=False)


class RolePermission(TimestampedModel):
    """Association: a Role grants a Permission."""

    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True
    )


class UserGroup(TimestampedModel):
    """A collection of users that receives roles via role bindings."""

    __tablename__ = "user_groups"

    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(default=False, nullable=False)


class UserGroupMember(TimestampedModel):
    """Association: a User belongs to a User Group."""

    __tablename__ = "user_group_members"
    __table_args__ = (
        UniqueConstraint("user_group_id", "user_id", name="uq_user_group_member"),
    )

    user_group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )


class RoleBinding(TimestampedModel):
    """Grants a Role to a User Group within a scope (GLOBAL today)."""

    __tablename__ = "role_bindings"
    __table_args__ = (
        UniqueConstraint(
            "user_group_id", "role_id", "scope_type", "scope_id",
            name="uq_role_binding",
        ),
    )

    user_group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope_type: Mapped[str] = mapped_column(
        String(16), default=SCOPE_GLOBAL, server_default=SCOPE_GLOBAL, nullable=False
    )
    scope_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
