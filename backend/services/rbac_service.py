"""RBAC permission resolution and idempotent seeding (1.2.1).

Resolution walks: User -> UserGroupMember -> RoleBinding -> Role ->
RolePermission -> Permission. The legacy ``UserRole.ADMIN`` acts as a
break-glass superuser (implicitly every permission) so an admin can never be
locked out of access management.

Seeding (``ensure_rbac_seed``) upserts the catalog in ``rbac_catalog`` and is
safe to run on every startup.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    Permission,
    Role,
    RoleBinding,
    RolePermission,
    User,
    UserGroup,
    UserGroupMember,
    UserRole,
)
from models.rbac import SCOPE_GLOBAL
from rbac_catalog import (
    ADMIN_GROUP_DESCRIPTION,
    ADMIN_GROUP_NAME,
    ADMIN_ROLE_NAME,
    ALL_PERMISSION_CODES,
    PERMISSIONS,
    SYSTEM_ROLES,
)
from utils.logging import get_logger

logger = get_logger(__name__)


def is_superuser(user: User) -> bool:
    """Legacy ADMIN role bypasses fine-grained permission checks."""
    return user.role == UserRole.ADMIN


async def get_user_permissions(db: AsyncSession, user: User) -> set[str]:
    """Effective permission codes for a user (superuser => all)."""
    if is_superuser(user):
        return set(ALL_PERMISSION_CODES)

    result = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(RoleBinding, RoleBinding.role_id == RolePermission.role_id)
        .join(UserGroupMember, UserGroupMember.user_group_id == RoleBinding.user_group_id)
        .where(UserGroupMember.user_id == user.id)
        .where(RoleBinding.scope_type == SCOPE_GLOBAL)
        .distinct()
    )
    return set(result.scalars().all())


async def user_has_permission(db: AsyncSession, user: User, code: str) -> bool:
    if is_superuser(user):
        return True
    return code in await get_user_permissions(db, user)


# --------------------------------------------------------------------------- #
# Seeding
# --------------------------------------------------------------------------- #
async def _seed_permissions(db: AsyncSession) -> dict[str, Permission]:
    existing = {
        p.code: p
        for p in (await db.execute(select(Permission))).scalars().all()
    }
    for spec in PERMISSIONS:
        perm = existing.get(spec.code)
        if perm is None:
            perm = Permission(
                code=spec.code, name=spec.name,
                category=spec.category, description=spec.description,
            )
            db.add(perm)
            existing[spec.code] = perm
        else:
            # Keep display metadata in sync with the catalog.
            perm.name = spec.name
            perm.category = spec.category
            perm.description = spec.description
    await db.flush()
    return existing


async def _seed_system_roles(
    db: AsyncSession, permissions: dict[str, Permission]
) -> dict[str, Role]:
    existing = {r.name: r for r in (await db.execute(select(Role))).scalars().all()}
    roles: dict[str, Role] = {}
    for name, spec in SYSTEM_ROLES.items():
        role = existing.get(name)
        if role is None:
            role = Role(name=name, description=spec["description"], is_system=True)
            db.add(role)
            await db.flush()
        else:
            role.description = spec["description"]
            role.is_system = True
        roles[name] = role

        # Reconcile the role's permission set to exactly the catalog set.
        current = {
            rp.permission_id: rp
            for rp in (
                await db.execute(
                    select(RolePermission).where(RolePermission.role_id == role.id)
                )
            ).scalars().all()
        }
        wanted_ids = {permissions[code].id for code in spec["permissions"]}
        for perm_id in wanted_ids - set(current):
            db.add(RolePermission(role_id=role.id, permission_id=perm_id))
        for perm_id, rp in current.items():
            if perm_id not in wanted_ids:
                await db.delete(rp)
    await db.flush()
    return roles


async def _seed_admin_group(db: AsyncSession, admin_role: Role) -> UserGroup:
    group = (
        await db.execute(select(UserGroup).where(UserGroup.name == ADMIN_GROUP_NAME))
    ).scalar_one_or_none()
    if group is None:
        group = UserGroup(
            name=ADMIN_GROUP_NAME, description=ADMIN_GROUP_DESCRIPTION, is_system=True
        )
        db.add(group)
        await db.flush()

    binding = (
        await db.execute(
            select(RoleBinding).where(
                RoleBinding.user_group_id == group.id,
                RoleBinding.role_id == admin_role.id,
                RoleBinding.scope_type == SCOPE_GLOBAL,
            )
        )
    ).scalar_one_or_none()
    if binding is None:
        db.add(
            RoleBinding(
                user_group_id=group.id, role_id=admin_role.id, scope_type=SCOPE_GLOBAL
            )
        )
        await db.flush()
    return group


async def _migrate_admins_into_group(db: AsyncSession, group: UserGroup) -> None:
    """Ensure every legacy ADMIN-role user is a member of the admin group."""
    admins = (
        await db.execute(select(User).where(User.role == UserRole.ADMIN))
    ).scalars().all()
    if not admins:
        return
    members = {
        m.user_id
        for m in (
            await db.execute(
                select(UserGroupMember).where(
                    UserGroupMember.user_group_id == group.id
                )
            )
        ).scalars().all()
    }
    for admin in admins:
        if admin.id not in members:
            db.add(UserGroupMember(user_group_id=group.id, user_id=admin.id))
    await db.flush()


async def ensure_rbac_seed(db: AsyncSession) -> None:
    """Idempotently seed permissions, system roles, the Administrators group and
    its binding, then migrate existing admins into that group."""
    permissions = await _seed_permissions(db)
    roles = await _seed_system_roles(db, permissions)
    admin_group = await _seed_admin_group(db, roles[ADMIN_ROLE_NAME])
    await _migrate_admins_into_group(db, admin_group)
    await db.commit()
    logger.info("RBAC catalog seeded (%d permissions)", len(permissions))
