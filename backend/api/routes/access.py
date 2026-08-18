"""Access Management endpoints: roles, user groups, role bindings, permissions.

All endpoints are guarded by fine-grained permissions. System roles and the
built-in Administrators group are protected from edits/deletes that would break
the authorization model or lock the last administrator out.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import RequirePermission
from database import get_db
from models import (
    Permission,
    Role,
    RoleBinding,
    RolePermission,
    User,
    UserGroup,
    UserGroupMember,
)
from rbac_catalog import ADMIN_GROUP_NAME, ADMIN_ROLE_NAME
from models.rbac import SCOPE_GLOBAL
from schemas.rbac import (
    PermissionResponse,
    RoleBindingCreate,
    RoleBindingResponse,
    RoleCreate,
    RoleDetailResponse,
    RoleGroupRef,
    RoleResponse,
    RoleUpdate,
    UserGroupCreate,
    UserGroupResponse,
    UserGroupUpdate,
)
from services.audit_service import (
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_UPDATE,
    record_audit,
)
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["access"])


# --------------------------------------------------------------------------- #
# Permissions (read-only catalog)
# --------------------------------------------------------------------------- #
@router.get(
    "/permissions",
    response_model=list[PermissionResponse],
    dependencies=[Depends(RequirePermission("permission.view"))],
)
async def list_permissions(db: AsyncSession = Depends(get_db)) -> list[Permission]:
    result = await db.execute(select(Permission).order_by(Permission.category, Permission.code))
    return list(result.scalars().all())


# --------------------------------------------------------------------------- #
# Roles
# --------------------------------------------------------------------------- #
async def _role_permission_codes(db: AsyncSession, role_id: uuid.UUID) -> list[str]:
    rows = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
        .order_by(Permission.code)
    )
    return list(rows.scalars().all())


async def _serialize_role(db: AsyncSession, role: Role) -> RoleResponse:
    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permission_codes=await _role_permission_codes(db, role.id),
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


async def _resolve_permissions(
    db: AsyncSession, codes: list[str]
) -> list[Permission]:
    if not codes:
        return []
    rows = await db.execute(select(Permission).where(Permission.code.in_(codes)))
    perms = list(rows.scalars().all())
    found = {p.code for p in perms}
    missing = set(codes) - found
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown permission code(s): {', '.join(sorted(missing))}",
        )
    return perms


@router.get(
    "/roles",
    response_model=list[RoleResponse],
    dependencies=[Depends(RequirePermission("role.view"))],
)
async def list_roles(db: AsyncSession = Depends(get_db)) -> list[RoleResponse]:
    roles = (await db.execute(select(Role).order_by(Role.name))).scalars().all()
    return [await _serialize_role(db, r) for r in roles]


@router.get(
    "/roles/{role_id}",
    response_model=RoleDetailResponse,
    dependencies=[Depends(RequirePermission("role.view"))],
)
async def get_role(
    role_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> RoleDetailResponse:
    """Role plus the groups bound to it and how many users inherit it — powers
    the Role Details page (no extra round-trips or separate bindings page)."""
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    groups = (
        await db.execute(
            select(UserGroup.id, UserGroup.name)
            .join(RoleBinding, RoleBinding.user_group_id == UserGroup.id)
            .where(RoleBinding.role_id == role_id, RoleBinding.scope_type == SCOPE_GLOBAL)
            .order_by(UserGroup.name)
        )
    ).all()
    group_ids = [row.id for row in groups]
    effective_users = 0
    if group_ids:
        effective_users = (
            await db.execute(
                select(func.count(func.distinct(UserGroupMember.user_id))).where(
                    UserGroupMember.user_group_id.in_(group_ids)
                )
            )
        ).scalar_one()

    return RoleDetailResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permission_codes=await _role_permission_codes(db, role.id),
        created_at=role.created_at,
        updated_at=role.updated_at,
        user_groups=[RoleGroupRef(id=row.id, name=row.name) for row in groups],
        effective_user_count=effective_users,
    )


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(RequirePermission("role.create")),
) -> RoleResponse:
    existing = await db.execute(select(Role).where(Role.name == payload.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role name already exists")
    perms = await _resolve_permissions(db, payload.permission_codes)
    role = Role(name=payload.name, description=payload.description, is_system=False)
    db.add(role)
    await db.flush()
    for perm in perms:
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    record_audit(
        db, actor, ACTION_CREATE, "role", role.name, role.id,
        new_value={"name": role.name, "permissions": payload.permission_codes},
    )
    await db.commit()
    await db.refresh(role)
    return await _serialize_role(db, role)


@router.patch("/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(RequirePermission("role.update")),
) -> RoleResponse:
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="System roles cannot be modified"
        )
    old = {"name": role.name, "permissions": await _role_permission_codes(db, role.id)}
    if payload.name is not None and payload.name != role.name:
        clash = await db.execute(
            select(Role).where(Role.name == payload.name, Role.id != role.id)
        )
        if clash.scalar_one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role name already exists")
        role.name = payload.name
    if payload.description is not None:
        role.description = payload.description
    if payload.permission_codes is not None:
        perms = await _resolve_permissions(db, payload.permission_codes)
        current = (
            await db.execute(
                select(RolePermission).where(RolePermission.role_id == role.id)
            )
        ).scalars().all()
        for rp in current:
            await db.delete(rp)
        await db.flush()
        for perm in perms:
            db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    record_audit(
        db, actor, ACTION_UPDATE, "role", role.name, role.id,
        old_value=old,
        new_value={"name": role.name, "permissions": payload.permission_codes},
    )
    await db.commit()
    await db.refresh(role)
    return await _serialize_role(db, role)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(RequirePermission("role.delete")),
) -> None:
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="System roles cannot be deleted"
        )
    record_audit(db, actor, ACTION_DELETE, "role", role.name, role.id)
    await db.delete(role)  # role_permissions / role_bindings cascade
    await db.commit()


# --------------------------------------------------------------------------- #
# User groups
# --------------------------------------------------------------------------- #
async def _serialize_group(db: AsyncSession, group: UserGroup) -> UserGroupResponse:
    member_ids = list(
        (
            await db.execute(
                select(UserGroupMember.user_id).where(
                    UserGroupMember.user_group_id == group.id
                )
            )
        ).scalars().all()
    )
    bound_roles = (
        await db.execute(
            select(Role.id, Role.name)
            .join(RoleBinding, RoleBinding.role_id == Role.id)
            .where(
                RoleBinding.user_group_id == group.id,
                RoleBinding.scope_type == SCOPE_GLOBAL,
            )
            .order_by(Role.name)
        )
    ).all()
    return UserGroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        is_system=group.is_system,
        member_ids=member_ids,
        member_count=len(member_ids),
        role_ids=[row.id for row in bound_roles],
        role_names=[row.name for row in bound_roles],
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


async def _validate_roles(db: AsyncSession, role_ids: list[uuid.UUID]) -> None:
    if not role_ids:
        return
    found = await db.execute(select(Role.id).where(Role.id.in_(role_ids)))
    if set(found.scalars().all()) != set(role_ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown role id")


async def _set_group_roles(
    db: AsyncSession, group: UserGroup, role_ids: list[uuid.UUID]
) -> None:
    """Sync a group's GLOBAL-scope role bindings to exactly ``role_ids``.

    This is the group-editor path onto the existing role_bindings table (the
    table and its API are unchanged). The built-in Administrator binding is
    never removed, so administrators cannot lock themselves out.
    """
    current = {
        b.role_id: b
        for b in (
            await db.execute(
                select(RoleBinding).where(
                    RoleBinding.user_group_id == group.id,
                    RoleBinding.scope_type == SCOPE_GLOBAL,
                )
            )
        ).scalars().all()
    }
    wanted = set(role_ids)

    admin_role_id = (
        await db.execute(select(Role.id).where(Role.name == ADMIN_ROLE_NAME))
    ).scalar_one_or_none()
    protected = group.name == ADMIN_GROUP_NAME and admin_role_id is not None

    for role_id in wanted - set(current):
        db.add(
            RoleBinding(
                user_group_id=group.id, role_id=role_id, scope_type=SCOPE_GLOBAL
            )
        )
    for role_id, binding in current.items():
        if role_id in wanted:
            continue
        if protected and role_id == admin_role_id:
            continue  # lockout guard: keep Administrators bound to Administrator
        await db.delete(binding)


async def _validate_users(db: AsyncSession, user_ids: list[uuid.UUID]) -> None:
    if not user_ids:
        return
    found = await db.execute(select(User.id).where(User.id.in_(user_ids)))
    if set(found.scalars().all()) != set(user_ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown user id")


async def _set_group_members(
    db: AsyncSession, group_id: uuid.UUID, user_ids: list[uuid.UUID]
) -> None:
    current = set(
        (
            await db.execute(
                select(UserGroupMember.user_id).where(
                    UserGroupMember.user_group_id == group_id
                )
            )
        ).scalars().all()
    )
    wanted = set(user_ids)
    for uid in wanted - current:
        db.add(UserGroupMember(user_group_id=group_id, user_id=uid))
    if current - wanted:
        stale = await db.execute(
            select(UserGroupMember).where(
                UserGroupMember.user_group_id == group_id,
                UserGroupMember.user_id.in_(current - wanted),
            )
        )
        for member in stale.scalars().all():
            await db.delete(member)


@router.get(
    "/user-groups",
    response_model=list[UserGroupResponse],
    dependencies=[Depends(RequirePermission("group.view"))],
)
async def list_user_groups(db: AsyncSession = Depends(get_db)) -> list[UserGroupResponse]:
    groups = (await db.execute(select(UserGroup).order_by(UserGroup.name))).scalars().all()
    return [await _serialize_group(db, g) for g in groups]


@router.post(
    "/user-groups", response_model=UserGroupResponse, status_code=status.HTTP_201_CREATED
)
async def create_user_group(
    payload: UserGroupCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(RequirePermission("group.create")),
) -> UserGroupResponse:
    existing = await db.execute(select(UserGroup).where(UserGroup.name == payload.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group name already exists")
    await _validate_users(db, payload.member_ids)
    await _validate_roles(db, payload.role_ids)
    group = UserGroup(name=payload.name, description=payload.description, is_system=False)
    db.add(group)
    await db.flush()
    await _set_group_members(db, group.id, payload.member_ids)
    await _set_group_roles(db, group, payload.role_ids)
    record_audit(db, actor, ACTION_CREATE, "user_group", group.name, group.id)
    await db.commit()
    await db.refresh(group)
    return await _serialize_group(db, group)


@router.patch("/user-groups/{group_id}", response_model=UserGroupResponse)
async def update_user_group(
    group_id: uuid.UUID,
    payload: UserGroupUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(RequirePermission("group.update")),
) -> UserGroupResponse:
    group = (
        await db.execute(select(UserGroup).where(UserGroup.id == group_id))
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    # Renaming a system group is blocked; membership can still be managed.
    if payload.name is not None and payload.name != group.name:
        if group.is_system:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="System groups cannot be renamed",
            )
        clash = await db.execute(
            select(UserGroup).where(UserGroup.name == payload.name, UserGroup.id != group.id)
        )
        if clash.scalar_one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group name already exists")
        group.name = payload.name
    if payload.description is not None:
        group.description = payload.description
    if payload.member_ids is not None:
        await _validate_users(db, payload.member_ids)
        await _set_group_members(db, group.id, payload.member_ids)
    if payload.role_ids is not None:
        await _validate_roles(db, payload.role_ids)
        await _set_group_roles(db, group, payload.role_ids)
    record_audit(db, actor, ACTION_UPDATE, "user_group", group.name, group.id)
    await db.commit()
    await db.refresh(group)
    return await _serialize_group(db, group)


@router.delete("/user-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(RequirePermission("group.delete")),
) -> None:
    group = (
        await db.execute(select(UserGroup).where(UserGroup.id == group_id))
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if group.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="System groups cannot be deleted"
        )
    record_audit(db, actor, ACTION_DELETE, "user_group", group.name, group.id)
    await db.delete(group)  # members / bindings cascade
    await db.commit()


# --------------------------------------------------------------------------- #
# Role bindings
# --------------------------------------------------------------------------- #
async def _serialize_binding(db: AsyncSession, binding: RoleBinding) -> RoleBindingResponse:
    group_name = (
        await db.execute(select(UserGroup.name).where(UserGroup.id == binding.user_group_id))
    ).scalar_one_or_none()
    role_name = (
        await db.execute(select(Role.name).where(Role.id == binding.role_id))
    ).scalar_one_or_none()
    return RoleBindingResponse(
        id=binding.id,
        user_group_id=binding.user_group_id,
        user_group_name=group_name or "?",
        role_id=binding.role_id,
        role_name=role_name or "?",
        scope_type=binding.scope_type,
        scope_id=binding.scope_id,
        created_at=binding.created_at,
        updated_at=binding.updated_at,
    )


@router.get(
    "/role-bindings",
    response_model=list[RoleBindingResponse],
    dependencies=[Depends(RequirePermission("binding.view"))],
)
async def list_role_bindings(db: AsyncSession = Depends(get_db)) -> list[RoleBindingResponse]:
    bindings = (await db.execute(select(RoleBinding))).scalars().all()
    return [await _serialize_binding(db, b) for b in bindings]


@router.post(
    "/role-bindings", response_model=RoleBindingResponse, status_code=status.HTTP_201_CREATED
)
async def create_role_binding(
    payload: RoleBindingCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(RequirePermission("binding.create")),
) -> RoleBindingResponse:
    group = (
        await db.execute(select(UserGroup).where(UserGroup.id == payload.user_group_id))
    ).scalar_one_or_none()
    role = (
        await db.execute(select(Role).where(Role.id == payload.role_id))
    ).scalar_one_or_none()
    if group is None or role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group or role not found")
    duplicate = await db.execute(
        select(RoleBinding).where(
            RoleBinding.user_group_id == payload.user_group_id,
            RoleBinding.role_id == payload.role_id,
            RoleBinding.scope_type == payload.scope_type,
            RoleBinding.scope_id == payload.scope_id,
        )
    )
    if duplicate.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Binding already exists")
    binding = RoleBinding(
        user_group_id=payload.user_group_id,
        role_id=payload.role_id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
    )
    db.add(binding)
    await db.flush()
    record_audit(
        db, actor, ACTION_CREATE, "role_binding",
        f"{group.name} -> {role.name}", binding.id,
    )
    await db.commit()
    await db.refresh(binding)
    return await _serialize_binding(db, binding)


@router.delete("/role-bindings/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role_binding(
    binding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(RequirePermission("binding.delete")),
) -> None:
    binding = (
        await db.execute(select(RoleBinding).where(RoleBinding.id == binding_id))
    ).scalar_one_or_none()
    if binding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding not found")
    group = (
        await db.execute(select(UserGroup).where(UserGroup.id == binding.user_group_id))
    ).scalar_one_or_none()
    role = (
        await db.execute(select(Role).where(Role.id == binding.role_id))
    ).scalar_one_or_none()
    # Lockout protection: keep the Administrators group bound to Administrator.
    if group and role and group.name == ADMIN_GROUP_NAME and role.name == ADMIN_ROLE_NAME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The built-in Administrator binding cannot be removed",
        )
    record_audit(
        db, actor, ACTION_DELETE, "role_binding",
        f"{group.name if group else '?'} -> {role.name if role else '?'}", binding.id,
    )
    await db.delete(binding)
    await db.commit()
