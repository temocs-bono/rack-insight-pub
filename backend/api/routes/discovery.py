"""SNMP Discovery + Import Wizard endpoints (F1/F2, admin only).

Discovery only collects identification data; importing is an explicit action
that reuses the existing bulk device-creation logic — no Installed Device is
ever created automatically.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.devices import bulk_create_devices
from auth.dependencies import RequirePermission
from database import get_db
from models import DiscoveredDevice, DiscoveryStatus, User
from schemas.device import DeviceBulkCreate, DeviceBulkItem, DeviceBulkCreateResult
from schemas.discovery import (
    DiscoveredDeviceResponse,
    DiscoveryImportRequest,
    DiscoveryScanRequest,
    DiscoveryScanResult,
)
from services.discovery.scanner import DiscoveryUnavailable
from services.discovery.service import expand_targets, get_discovery, run_discovery
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(
    prefix="/discovery",
    tags=["discovery"],
    dependencies=[Depends(RequirePermission("discovery.view"))],
)


@router.get("", response_model=list[DiscoveredDeviceResponse])
async def list_discoveries(
    pending_only: bool = True, db: AsyncSession = Depends(get_db)
) -> list[DiscoveredDevice]:
    query = select(DiscoveredDevice).order_by(DiscoveredDevice.updated_at.desc())
    if pending_only:
        query = query.where(DiscoveredDevice.status == DiscoveryStatus.PENDING)
    return list((await db.execute(query)).scalars().all())


@router.post(
    "/scan", response_model=DiscoveryScanResult,
    dependencies=[Depends(RequirePermission("discovery.scan"))],
)
async def scan(
    payload: DiscoveryScanRequest, db: AsyncSession = Depends(get_db)
) -> DiscoveryScanResult:
    try:
        scanned = len(expand_targets(payload.targets))
        discovered = await run_discovery(
            db, payload.targets, payload.community, payload.timeout
        )
        return DiscoveryScanResult(
            scanned=scanned,
            reachable=len(discovered),
            discovered=[DiscoveredDeviceResponse.model_validate(d) for d in discovered],
        )
    except DiscoveryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SNMP support is not installed on the server",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Discovery scan failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Discovery scan failed"
        ) from exc


@router.post(
    "/import", response_model=DeviceBulkCreateResult,
    dependencies=[Depends(RequirePermission("discovery.import"))],
)
async def import_discovered(
    payload: DiscoveryImportRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("discovery.import")),
) -> DeviceBulkCreateResult:
    """Create Installed Devices from selected discoveries (reuses bulk create)."""
    try:
        records = {
            item.discovered_id: await get_discovery(db, item.discovered_id)
            for item in payload.items
        }

        bulk_payload = DeviceBulkCreate(
            rack_id=payload.rack_id,
            template_id=payload.template_id,
            redfish_credential_id=payload.redfish_credential_id,
            ssh_credential_id=payload.ssh_credential_id,
            snmp_credential_id=payload.snmp_credential_id,
            items=[
                DeviceBulkItem(
                    hostname=item.hostname,
                    management_ip=item.management_ip
                    or records[item.discovered_id].ip_address,
                    ilo_ip=item.ilo_ip,
                    u_position=item.u_position,
                )
                for item in payload.items
            ],
        )
        result = await bulk_create_devices(bulk_payload, db=db, admin=admin)

        # Mark successfully imported discoveries (matched by hostname).
        created_by_host = {d.hostname: d.id for d in result.created}
        for item in payload.items:
            device_id = created_by_host.get(item.hostname)
            if device_id is not None:
                record = records[item.discovered_id]
                record.status = DiscoveryStatus.IMPORTED
                record.imported_device_id = device_id
        await db.commit()
        return result
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.exception("Discovery import failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Discovery import failed"
        ) from exc


@router.delete(
    "/{discovery_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("discovery.import"))],
)
async def ignore_discovery(
    discovery_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    record = await get_discovery(db, discovery_id)
    record.status = DiscoveryStatus.IGNORED
    await db.commit()
