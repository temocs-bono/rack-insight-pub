"""Device CRUD, search, latest inventory, health, and refresh endpoints."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import RequirePermission
from cache.redis_cache import cache_delete, device_inventory_key
from database import get_db
from models import (
    CPU,
    Device,
    DeviceStatus,
    DeviceTemplate,
    Firmware,
    Rack,
    RackUnit,
    Sensor,
    Snapshot,
    Storage,
    User,
)
from schemas.device import (
    MAX_BULK_DEVICES,
    VALID_COLLECTOR_TYPES,
    DeviceBulkCreate,
    DeviceBulkCreateError,
    DeviceBulkCreateResult,
    DeviceCreate,
    DeviceDetailResponse,
    DevicePositionUpdate,
    DeviceResponse,
    DeviceSearchPage,
    DeviceSearchResult,
    DeviceUpdate,
)
from schemas.inventory import DeviceInventoryResponse
from services.audit_service import (
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_UPDATE,
    record_audit,
    snapshot_entity,
)
from services.drift_service import get_device_drift
from services.health_service import compute_health, get_device_health
from services.inventory_service import get_device_inventory, get_latest_snapshot
from services.placement_service import validate_placement
from services.refresh_service import refresh_device
from schemas.drift import DriftReport
from schemas.operations import DeviceHealthResponse
from utils.crypto import encrypt_secret
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(
    prefix="/devices",
    tags=["devices"],
    dependencies=[Depends(RequirePermission("device.view"))],
)

_SECRET_FIELDS = {
    "ilo_password": "ilo_password_encrypted",
    "ssh_password": "ssh_password_encrypted",
    "snmp_community": "snmp_community_encrypted",
}


def _serialize_collector_types(types: list[str] | None) -> str | None:
    """Validate and join the collector type list into the stored string."""
    if not types:
        return None
    normalized = [t.strip().upper() for t in types if t.strip()]
    invalid = set(normalized) - VALID_COLLECTOR_TYPES
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid collector types: {', '.join(sorted(invalid))}",
        )
    return ",".join(dict.fromkeys(normalized)) or None


async def _apply_template(
    db: AsyncSession, data: dict, template_id: uuid.UUID | None
) -> None:
    """Inherit vendor/model from the template when not explicitly provided."""
    if template_id is None:
        return
    template = (
        await db.execute(select(DeviceTemplate).where(DeviceTemplate.id == template_id))
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Device template not found",
        )
    if not data.get("vendor"):
        data["vendor"] = template.vendor
    if not data.get("model"):
        data["model"] = template.model


async def _require_rack(db: AsyncSession, rack_id: uuid.UUID) -> Rack:
    rack = (await db.execute(select(Rack).where(Rack.id == rack_id))).scalar_one_or_none()
    if rack is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rack not found")
    return rack


async def _ensure_hostname_free(
    db: AsyncSession, rack_id: uuid.UUID, hostname: str, exclude_device_id: uuid.UUID | None = None
) -> None:
    """Hostnames must be unique within a rack (consistent with bulk creation)."""
    query = select(Device.id).where(
        Device.rack_id == rack_id, Device.hostname == hostname
    )
    if exclude_device_id is not None:
        query = query.where(Device.id != exclude_device_id)
    if (await db.execute(query)).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Hostname '{hostname}' already exists in this rack",
        )


async def _get_device(db: AsyncSession, device_id: uuid.UUID) -> Device:
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device


@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    rack_id: uuid.UUID | None = None,
    page: int | None = None,
    page_size: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[Device]:
    """All devices (optionally per rack); pass page/page_size to paginate.
    /devices/search offers filtered pagination with totals."""
    query = select(Device).order_by(Device.hostname)
    if rack_id is not None:
        query = query.where(Device.rack_id == rack_id)
    if page is not None and page_size is not None:
        query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return list(result.scalars().all())


DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200


def _serial_exists(pattern: str):
    """EXISTS clause matching a serial in any snapshot's CPUs or storages."""
    cpu_match = exists(
        select(CPU.id)
        .join(Snapshot, Snapshot.id == CPU.snapshot_id)
        .where(Snapshot.device_id == Device.id, CPU.serial.ilike(pattern))
    )
    storage_match = exists(
        select(Storage.id)
        .join(Snapshot, Snapshot.id == Storage.snapshot_id)
        .where(Snapshot.device_id == Device.id, Storage.serial.ilike(pattern))
    )
    return or_(cpu_match, storage_match)


@router.get("/search", response_model=DeviceSearchPage)
async def search_devices(
    q: str | None = Query(default=None, description="Matches hostname, vendor, model, serial"),
    hostname: str | None = None,
    serial: str | None = None,
    vendor: str | None = None,
    model: str | None = None,
    cluster_id: uuid.UUID | None = None,
    rack_id: uuid.UUID | None = None,
    device_status: DeviceStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: AsyncSession = Depends(get_db),
) -> DeviceSearchPage:
    """Inventory search with filters and server-side pagination (F5)."""
    try:
        query = select(Device)
        if q:
            pattern = f"%{q}%"
            query = query.where(
                or_(
                    Device.hostname.ilike(pattern),
                    Device.display_name.ilike(pattern),
                    Device.vendor.ilike(pattern),
                    Device.model.ilike(pattern),
                    _serial_exists(pattern),
                )
            )
        if hostname:
            query = query.where(
                or_(
                    Device.hostname.ilike(f"%{hostname}%"),
                    Device.display_name.ilike(f"%{hostname}%"),
                )
            )
        if serial:
            query = query.where(_serial_exists(f"%{serial}%"))
        if vendor:
            query = query.where(Device.vendor.ilike(f"%{vendor}%"))
        if model:
            query = query.where(Device.model.ilike(f"%{model}%"))
        if rack_id is not None:
            query = query.where(Device.rack_id == rack_id)
        if cluster_id is not None:
            query = query.where(
                Device.rack_id.in_(select(Rack.id).where(Rack.cluster_id == cluster_id))
            )
        if device_status is not None:
            query = query.where(Device.status == device_status)

        total = (
            await db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()
        result = await db.execute(
            query.order_by(Device.hostname).offset((page - 1) * page_size).limit(page_size)
        )
        items: list[DeviceSearchResult] = []
        for device in result.scalars().all():
            item = DeviceSearchResult.model_validate(device)
            item.rack_name = device.rack.name if device.rack else None
            item.cluster_name = (
                device.rack.cluster.name if device.rack and device.rack.cluster else None
            )
            item.cluster_id = device.rack.cluster_id if device.rack else None
            items.append(item)
        return DeviceSearchPage(items=items, total=total, page=page, page_size=page_size)
    except Exception as exc:
        logger.exception("Device search failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Device search failed"
        ) from exc


@router.get("/{device_id}", response_model=DeviceDetailResponse)
async def get_device(
    device_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> DeviceDetailResponse:
    try:
        device = await _get_device(db, device_id)
        detail = DeviceDetailResponse.model_validate(device)

        snapshot = await get_latest_snapshot(db, device_id)
        if snapshot is not None:
            detail.last_refresh = snapshot.collected_at
            sensors = (
                (await db.execute(select(Sensor).where(Sensor.snapshot_id == snapshot.id)))
                .scalars().all()
            )
            storages = (
                (await db.execute(select(Storage).where(Storage.snapshot_id == snapshot.id)))
                .scalars().all()
            )
            firmwares = (
                (await db.execute(select(Firmware).where(Firmware.snapshot_id == snapshot.id)))
                .scalars().all()
            )
            cpus = (
                (await db.execute(select(CPU).where(CPU.snapshot_id == snapshot.id)))
                .scalars().all()
            )
            health = compute_health(
                device.status, snapshot, list(sensors), list(storages), list(firmwares)
            )
            detail.health_score = health.score
            detail.health_label = health.label
            serials = [c.serial for c in cpus if c.serial]
            detail.serial = serials[0] if serials else None
        return detail
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Device detail failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Device detail failed"
        ) from exc


@router.get("/{device_id}/inventory", response_model=DeviceInventoryResponse)
async def get_inventory(
    device_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> DeviceInventoryResponse:
    try:
        await _get_device(db, device_id)
        return await get_device_inventory(db, device_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Inventory read failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Inventory read failed"
        ) from exc


@router.get("/{device_id}/drift", response_model=DriftReport)
async def get_drift(
    device_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> DriftReport:
    """Hardware drift between the two most recent successful collections.

    Kept for API backward compatibility (1.2.x). The 1.3.0 UI uses Alerts and
    Device History instead; the Event Engine performs the comparison."""
    try:
        await _get_device(db, device_id)
        return await get_device_drift(db, device_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Drift detection failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Drift detection failed"
        ) from exc


@router.get("/{device_id}/health", response_model=DeviceHealthResponse)
async def get_health(
    device_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> DeviceHealthResponse:
    """Device Health (1.3.0): overall health, sensor groups, storage/memory/
    network health, and a health timeline across recent snapshots."""
    try:
        device = await _get_device(db, device_id)
        return await get_device_health(db, device)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Device health failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Device health failed"
        ) from exc


@router.post(
    "/{device_id}/refresh",
    response_model=DeviceInventoryResponse,
    dependencies=[Depends(RequirePermission("collector.run"))],
)
async def refresh(
    device_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> DeviceInventoryResponse:
    try:
        return await refresh_device(db, device_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Device refresh failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Device refresh failed"
        ) from exc


@router.post(
    "",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_device(
    payload: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("device.install")),
) -> Device:
    try:
        rack = await _require_rack(db, payload.rack_id)
        await _ensure_hostname_free(db, payload.rack_id, payload.hostname)
        if payload.u_position is not None:
            await validate_placement(db, rack, payload.u_position, payload.height)

        data = payload.model_dump(exclude={"u_position", "height"})
        for plain_field, encrypted_field in _SECRET_FIELDS.items():
            data[encrypted_field] = encrypt_secret(data.pop(plain_field, None))
        data["collector_types"] = _serialize_collector_types(data.pop("collector_types", None))
        await _apply_template(db, data, payload.template_id)
        device = Device(**data)
        db.add(device)
        await db.flush()

        if payload.u_position is not None:
            db.add(
                RackUnit(
                    rack_id=payload.rack_id,
                    u_position=payload.u_position,
                    height=payload.height,
                    device_id=device.id,
                )
            )
        record_audit(
            db, admin, ACTION_CREATE, "device", device.hostname, device.id,
            new_value=snapshot_entity(device),
        )
        await db.commit()
        await db.refresh(device)
        logger.info("Device %s registered", device.hostname)
        return device
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.exception("Device creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Device creation failed"
        ) from exc


@router.post(
    "/bulk",
    response_model=DeviceBulkCreateResult,
    status_code=status.HTTP_201_CREATED,
)
async def bulk_create_devices(
    payload: DeviceBulkCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("device.install")),
) -> DeviceBulkCreateResult:
    """Install multiple instances in one transaction (P3 / 1.1.2 wizard).

    With `items`, each reviewed row carries its own hostname, IPs, credential
    and optional U position (top-level fields are defaults). Without `items`,
    hostnames come from `hostnames` or `hostname_prefix` + sequential number
    (1.1.1 behavior). Duplicate hostnames in the rack are skipped; the whole
    operation is one transaction.
    """
    try:
        collector_types = _serialize_collector_types(payload.collector_types)
        base: dict = {"vendor": payload.vendor, "model": payload.model}
        await _apply_template(db, base, payload.template_id)

        # Normalize both modes into a list of per-row specs.
        rows: list[dict] = []
        if payload.items is not None:
            for item in payload.items:
                rows.append(
                    {
                        "hostname": item.hostname.strip(),
                        "management_ip": item.management_ip or None,
                        "ilo_ip": item.ilo_ip or None,
                        "redfish_credential_id": item.redfish_credential_id
                        or payload.redfish_credential_id,
                        "ssh_credential_id": item.ssh_credential_id
                        or payload.ssh_credential_id,
                        "snmp_credential_id": item.snmp_credential_id
                        or payload.snmp_credential_id,
                        "u_position": item.u_position,
                        "height": item.height or 1,
                    }
                )
        else:
            if payload.hostnames:
                names = [h.strip() for h in payload.hostnames if h.strip()]
            elif payload.hostname_prefix and payload.quantity:
                names = [
                    f"{payload.hostname_prefix}-{str(i).zfill(payload.pad_width)}"
                    for i in range(
                        payload.start_index, payload.start_index + payload.quantity
                    )
                ]
            else:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Provide items, hostnames, or hostname_prefix + quantity",
                )
            rows = [
                {
                    "hostname": name,
                    "management_ip": None,
                    "ilo_ip": None,
                    "redfish_credential_id": payload.redfish_credential_id,
                    "ssh_credential_id": payload.ssh_credential_id,
                    "snmp_credential_id": payload.snmp_credential_id,
                    "u_position": None,
                    "height": 1,
                }
                for name in names
            ]

        if len(rows) > MAX_BULK_DEVICES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"At most {MAX_BULK_DEVICES} devices per operation",
            )

        names = [r["hostname"] for r in rows]
        existing = set(
            (
                await db.execute(
                    select(Device.hostname).where(
                        Device.rack_id == payload.rack_id, Device.hostname.in_(names)
                    )
                )
            )
            .scalars().all()
        )

        # Existing occupied U ranges in the rack, for optional placement.
        occupied: set[int] = set()
        for unit in (
            (
                await db.execute(
                    select(RackUnit).where(RackUnit.rack_id == payload.rack_id)
                )
            )
            .scalars().all()
        ):
            occupied |= set(range(unit.u_position, unit.u_position + unit.height))
        rack = (
            await db.execute(select(Rack).where(Rack.id == payload.rack_id))
        ).scalar_one_or_none()
        if rack is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Rack not found"
            )

        created: list[Device] = []
        placements: list[tuple[Device, int, int]] = []
        skipped: list[str] = []
        errors: list[DeviceBulkCreateError] = []
        seen: set[str] = set()
        seen_mgmt: set[str] = set()
        seen_ilo: set[str] = set()
        for row in rows:
            name = row["hostname"]
            if not name or name in existing or name in seen:
                skipped.append(name)
                continue
            seen.add(name)

            # Duplicate IP detection within the batch (Required Fix 2).
            mgmt, ilo = row["management_ip"], row["ilo_ip"]
            if mgmt and mgmt in seen_mgmt:
                errors.append(
                    DeviceBulkCreateError(
                        hostname=name, error=f"Duplicate Management IP {mgmt}"
                    )
                )
            elif mgmt:
                seen_mgmt.add(mgmt)
            if ilo and ilo in seen_ilo:
                errors.append(
                    DeviceBulkCreateError(hostname=name, error=f"Duplicate iLO IP {ilo}")
                )
            elif ilo:
                seen_ilo.add(ilo)
            device = Device(
                rack_id=payload.rack_id,
                template_id=payload.template_id,
                hostname=name,
                device_type=payload.device_type,
                vendor=base["vendor"],
                model=base["model"],
                management_ip=row["management_ip"],
                ilo_ip=row["ilo_ip"],
                orientation=payload.orientation,
                collector_types=collector_types,
                redfish_credential_id=row["redfish_credential_id"],
                ssh_credential_id=row["ssh_credential_id"],
                snmp_credential_id=row["snmp_credential_id"],
            )
            db.add(device)
            created.append(device)

            u = row["u_position"]
            if u is not None:
                height = row["height"]
                span = set(range(u, u + height))
                if u + height - 1 > rack.height:
                    errors.append(
                        DeviceBulkCreateError(
                            hostname=name,
                            error=f"U{u} (+{height}U) exceeds rack height {rack.height}U",
                        )
                    )
                elif span & occupied:
                    errors.append(
                        DeviceBulkCreateError(
                            hostname=name, error=f"U{u} overlaps an occupied slot"
                        )
                    )
                else:
                    occupied |= span
                    placements.append((device, u, height))

        if errors:
            # Reviewed-table placement conflicts are a validation failure:
            # commit nothing so the admin can fix the table and resubmit.
            await db.rollback()
            return DeviceBulkCreateResult(created=[], skipped=skipped, errors=errors)

        await db.flush()
        for device, u, height in placements:
            db.add(
                RackUnit(
                    rack_id=payload.rack_id,
                    u_position=u,
                    height=height,
                    device_id=device.id,
                )
            )
        for device in created:
            record_audit(
                db, admin, ACTION_CREATE, "device", device.hostname, device.id,
                new_value=snapshot_entity(device),
            )
        await db.commit()
        for device in created:
            await db.refresh(device)
        logger.info(
            "Bulk device creation: %d created, %d skipped", len(created), len(skipped)
        )
        return DeviceBulkCreateResult(
            created=[DeviceResponse.model_validate(d) for d in created],
            skipped=skipped,
            errors=errors,
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        logger.exception("Bulk device creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bulk device creation failed",
        ) from exc


@router.patch("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: uuid.UUID,
    payload: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("device.update")),
) -> Device:
    device = await _get_device(db, device_id)
    old = snapshot_entity(device)
    data = payload.model_dump(exclude_unset=True)

    # Validate identity/reference changes before applying (Required Fix 3/5).
    target_rack_id = data.get("rack_id", device.rack_id)
    if "hostname" in data and (
        data["hostname"] != device.hostname or target_rack_id != device.rack_id
    ):
        await _ensure_hostname_free(
            db, target_rack_id, data["hostname"], exclude_device_id=device.id
        )
    if data.get("template_id") is not None:
        template_data: dict = {}
        await _apply_template(db, template_data, data["template_id"])

    # Moving a device to another rack invalidates its old U placement — clear
    # it so no rack_unit is stranded in the previous rack (device becomes
    # unplaced and is positioned again via drag-and-drop).
    rack_changed = "rack_id" in data and data["rack_id"] != device.rack_id
    if rack_changed:
        for unit in (
            (await db.execute(select(RackUnit).where(RackUnit.device_id == device_id)))
            .scalars().all()
        ):
            await db.delete(unit)

    for plain_field, encrypted_field in _SECRET_FIELDS.items():
        if plain_field in data:
            data[encrypted_field] = encrypt_secret(data.pop(plain_field))
    if "collector_types" in data:
        data["collector_types"] = _serialize_collector_types(data["collector_types"])
    for key, value in data.items():
        setattr(device, key, value)
    record_audit(
        db, admin, ACTION_UPDATE, "device", device.hostname, device.id,
        old_value=old, new_value=snapshot_entity(device),
    )
    await db.commit()
    await db.refresh(device)
    return device


@router.put(
    "/{device_id}/position",
    response_model=DeviceResponse,
    dependencies=[Depends(RequirePermission("device.move"))],
)
async def move_device(
    device_id: uuid.UUID,
    payload: DevicePositionUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("device.move")),
) -> Device:
    """Assign/move a device to a U position (drag & drop / U selection).

    Optionally moves it into a different rack (`rack_id`) — the 'assign to
    rack' action from the Management workflow.
    """
    device = await _get_device(db, device_id)
    try:
        target_rack_id = payload.rack_id or device.rack_id
        rack = (
            await db.execute(select(Rack).where(Rack.id == target_rack_id))
        ).scalar_one_or_none()
        if rack is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Target rack not found"
            )

        unit_result = await db.execute(
            select(RackUnit).where(RackUnit.device_id == device_id)
        )
        unit = unit_result.scalars().first()
        height = payload.height if payload.height is not None else (unit.height if unit else 1)

        # Exclude the device's own unit by its id (not device_id) so orphan or
        # NULL-device rows are never silently skipped in the overlap check.
        await validate_placement(
            db,
            rack,
            payload.u_position,
            height,
            exclude_unit_id=unit.id if unit is not None else None,
        )

        device.rack_id = target_rack_id
        if unit is None:
            db.add(
                RackUnit(
                    rack_id=target_rack_id,
                    u_position=payload.u_position,
                    height=height,
                    device_id=device_id,
                )
            )
        else:
            unit.rack_id = target_rack_id
            unit.u_position = payload.u_position
            unit.height = height
        record_audit(
            db, admin, ACTION_UPDATE, "device", device.hostname, device.id,
            new_value={"rack_id": str(target_rack_id), "u_position": payload.u_position},
        )
        await db.commit()
        await db.refresh(device)
        return device
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        logger.exception("Device move failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Device move failed"
        ) from exc


@router.delete(
    "/{device_id}/position",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("device.move"))],
)
async def unassign_device(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("device.move")),
) -> None:
    """Remove a device from its rack slot (uninstall) without deleting it."""
    device = await _get_device(db, device_id)
    try:
        units = (
            (await db.execute(select(RackUnit).where(RackUnit.device_id == device_id)))
            .scalars().all()
        )
        for unit in units:
            await db.delete(unit)
        record_audit(
            db, admin, ACTION_UPDATE, "device", device.hostname, device.id,
            old_value={"placed": True}, new_value={"placed": False},
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("Device unassign failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Device unassign failed"
        ) from exc


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("device.delete")),
) -> None:
    device = await _get_device(db, device_id)
    await cache_delete(device_inventory_key(str(device_id)))
    # Remove rack placement first so no orphan rack_unit (device_id NULL) is
    # left occupying a U slot — the FK is ON DELETE SET NULL, which would
    # otherwise strand the placement and corrupt the rack layout.
    for unit in (
        (await db.execute(select(RackUnit).where(RackUnit.device_id == device_id)))
        .scalars().all()
    ):
        await db.delete(unit)
    record_audit(
        db, admin, ACTION_DELETE, "device", device.hostname, device.id,
        old_value=snapshot_entity(device),
    )
    await db.delete(device)
    await db.commit()
