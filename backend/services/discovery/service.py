"""Discovery orchestration (F1/F2).

Expands scan targets into IPs, probes them over SNMP concurrently, and upserts
one PENDING DiscoveredDevice per reachable host. Discovery NEVER creates
Installed Devices — import is an explicit, separate admin action.
"""
import asyncio
import ipaddress
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import DiscoveredDevice, DiscoveryStatus
from services.discovery.scanner import (
    DiscoveryScanner,
    SnmpScanner,
    infer_device_type,
    infer_vendor,
)
from utils.logging import get_logger

logger = get_logger(__name__)

MAX_SCAN_TARGETS = 1024
DEFAULT_PROBE_TIMEOUT = 2.0
SCAN_CONCURRENCY = 32

# Default scanner factory — overridable in tests via patching.
_scanner_factory = SnmpScanner


def set_scanner_factory(factory) -> None:
    global _scanner_factory
    _scanner_factory = factory


def expand_targets(targets: list[str]) -> list[str]:
    """Expand a mix of single IPs and CIDR blocks into individual host IPs."""
    ips: list[str] = []
    seen: set[str] = set()
    for raw in targets:
        entry = raw.strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                network = ipaddress.ip_network(entry, strict=False)
                hosts = network.hosts() if network.num_addresses > 2 else network
                for host in hosts:
                    text = str(host)
                    if text not in seen:
                        seen.add(text)
                        ips.append(text)
            else:
                ip = str(ipaddress.ip_address(entry))
                if ip not in seen:
                    seen.add(ip)
                    ips.append(ip)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid scan target '{entry}': {exc}",
            ) from exc
        if len(ips) > MAX_SCAN_TARGETS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Scan targets exceed the {MAX_SCAN_TARGETS}-address limit",
            )
    return ips


async def run_discovery(
    db: AsyncSession,
    targets: list[str],
    community: str,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
    scanner: DiscoveryScanner | None = None,
) -> list[DiscoveredDevice]:
    """Probe every target and upsert PENDING discoveries. Returns the reachable
    discoveries found in this scan."""
    ips = expand_targets(targets)
    if not ips:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No scan targets provided",
        )

    active = scanner if scanner is not None else _scanner_factory()
    semaphore = asyncio.Semaphore(SCAN_CONCURRENCY)

    async def probe(ip: str):
        async with semaphore:
            return await active.probe(ip, community, timeout)

    results = await asyncio.gather(*(probe(ip) for ip in ips))
    reachable = [r for r in results if r.reachable]
    logger.info("Discovery scan: %d/%d hosts reachable", len(reachable), len(ips))

    discovered: list[DiscoveredDevice] = []
    for result in reachable:
        # Reuse an existing PENDING row for the same IP instead of duplicating.
        existing = (
            await db.execute(
                select(DiscoveredDevice).where(
                    DiscoveredDevice.ip_address == result.ip_address,
                    DiscoveredDevice.status == DiscoveryStatus.PENDING,
                )
            )
        ).scalars().first()
        record = existing or DiscoveredDevice(
            ip_address=result.ip_address, status=DiscoveryStatus.PENDING
        )
        record.sysname = result.sysname
        record.sysdescr = result.sysdescr
        record.sysobjectid = result.sysobjectid
        record.vendor = infer_vendor(result.sysdescr)
        record.device_type_guess = infer_device_type(result.sysdescr)
        if existing is None:
            db.add(record)
        discovered.append(record)

    await db.commit()
    for record in discovered:
        await db.refresh(record)
    return discovered


async def get_discovery(db: AsyncSession, discovery_id: uuid.UUID) -> DiscoveredDevice:
    record = (
        await db.execute(
            select(DiscoveredDevice).where(DiscoveredDevice.id == discovery_id)
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Discovery not found"
        )
    return record
