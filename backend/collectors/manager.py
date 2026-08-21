"""CollectorManager: run all applicable collectors in parallel, merge results,
and persist a new Snapshot.

Fail-safe policy: if every collector fails, no snapshot is created and the
previous data is preserved untouched.
"""
import asyncio
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from collectors.base import BaseCollector, CollectorResult, DeviceCredentials
from collectors.cisco.collector import CiscoCollector
from collectors.redfish.collector import RedfishCollector
from collectors.ssh.collector import SSHCollector
from collectors.virsh.collector import VirshCollector
from config import get_settings
from models import (
    CPU,
    NIC,
    VM,
    Device,
    DeviceStatus,
    Disk,
    Firmware,
    Memory,
    Network,
    Sensor,
    Snapshot,
    Storage,
    SwitchInventory,
)
from utils.crypto import decrypt_secret
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CollectionOutcome:
    snapshot: Snapshot | None
    results: list[CollectorResult]
    status: DeviceStatus
    system: dict[str, Any]


def build_credentials(device: Device) -> DeviceCredentials:
    """Resolve connection info. Named credentials (Credential store) take
    precedence over the legacy inline per-device fields."""
    ilo_username = device.ilo_username
    ilo_password = decrypt_secret(device.ilo_password_encrypted)
    if device.redfish_credential is not None:
        ilo_username = device.redfish_credential.username or ilo_username
        ilo_password = decrypt_secret(device.redfish_credential.password_encrypted) or ilo_password

    ssh_username = device.ssh_username
    ssh_password = decrypt_secret(device.ssh_password_encrypted)
    if device.ssh_credential is not None:
        ssh_username = device.ssh_credential.username or ssh_username
        ssh_password = decrypt_secret(device.ssh_credential.password_encrypted) or ssh_password

    snmp_community = decrypt_secret(device.snmp_community_encrypted)
    if device.snmp_credential is not None:
        snmp_community = (
            decrypt_secret(device.snmp_credential.password_encrypted) or snmp_community
        )

    collector_types: frozenset[str] | None = None
    if device.collector_types:
        collector_types = frozenset(
            t.strip().upper() for t in device.collector_types.split(",") if t.strip()
        )

    return DeviceCredentials(
        hostname=device.hostname,
        device_type=device.device_type.value,
        management_ip=device.management_ip,

        ilo_ip=device.ilo_ip,
        ilo_port=device.ilo_port,
        ilo_use_https=device.ilo_use_https,
        ilo_username=ilo_username,
        ilo_password=ilo_password,

        ssh_username=ssh_username,
        ssh_password=ssh_password,
        snmp_community=snmp_community,
        collector_types=collector_types,
    )


def default_collectors() -> list[BaseCollector]:
    settings = get_settings()
    kwargs = {
        "timeout_seconds": settings.collector_timeout_seconds,
        "retry_count": settings.collector_retry_count,
    }
    return [
        RedfishCollector(**kwargs),
        SSHCollector(**kwargs),
        VirshCollector(**kwargs),
        CiscoCollector(**kwargs),
    ]


class CollectorManager:
    def __init__(self, collectors: list[BaseCollector] | None = None) -> None:
        self.collectors = collectors if collectors is not None else default_collectors()

    async def collect_device(self, db: AsyncSession, device: Device) -> CollectionOutcome:
        """Run all collectors for one device and persist a snapshot on success."""
        creds = build_credentials(device)
        results = list(
            await asyncio.gather(*(collector.collect(creds) for collector in self.collectors))
        )

        by_name = {result.collector_name: result for result in results}
        ran = [r for r in results if not r.skipped]
        succeeded = [r for r in ran if r.success]

        status = self._derive_status(ran, succeeded)
        merged_system: dict[str, Any] = {}
        for result in succeeded:
            merged_system.update({k: v for k, v in result.system.items() if v is not None})

        if not succeeded:
            logger.error(
                "All collectors failed for device %s; keeping previous snapshot",
                device.hostname,
            )
            return CollectionOutcome(snapshot=None, results=results, status=status, system={})

        snapshot = self._build_snapshot(device, by_name, succeeded)
        db.add(snapshot)
        await db.flush()
        self._persist_inventory(db, snapshot, succeeded)
        logger.info(
            "Snapshot %s created for device %s (duration_ms=%d)",
            snapshot.id, device.hostname, snapshot.duration_ms,
        )
        return CollectionOutcome(
            snapshot=snapshot, results=results, status=status, system=merged_system
        )

    @staticmethod
    def _derive_status(
        ran: list[CollectorResult], succeeded: list[CollectorResult]
    ) -> DeviceStatus:
        if not ran:
            return DeviceStatus.UNKNOWN
        if len(succeeded) == len(ran):
            return DeviceStatus.ONLINE
        if succeeded:
            return DeviceStatus.WARNING
        return DeviceStatus.OFFLINE

    @staticmethod
    def _build_snapshot(
        device: Device,
        by_name: dict[str, CollectorResult],
        succeeded: list[CollectorResult],
    ) -> Snapshot:
        def ok(name: str) -> bool:
            result = by_name.get(name)
            return bool(result and result.success and not result.skipped)

        return Snapshot(
            device_id=device.id,
            collector_version=get_settings().collector_version,
            redfish_success=ok("redfish"),
            ssh_success=ok("ssh"),
            virsh_success=ok("virsh"),
            duration_ms=max((result.duration_ms for result in succeeded), default=0),
        )

    @staticmethod
    def _persist_inventory(
        db: AsyncSession, snapshot: Snapshot, succeeded: list[CollectorResult]
    ) -> None:
        for result in succeeded:
            for cpu in result.cpus:
                db.add(CPU(snapshot_id=snapshot.id, **cpu))
            for memory in result.memories:
                db.add(Memory(snapshot_id=snapshot.id, **memory))
            for nic in result.nics:
                db.add(NIC(snapshot_id=snapshot.id, **nic))
            for firmware in result.firmwares:
                db.add(Firmware(snapshot_id=snapshot.id, **firmware))
            for storage_data in result.storages:
                disks = storage_data.pop("disks", [])
                storage = Storage(snapshot_id=snapshot.id, **storage_data)
                db.add(storage)
                for disk in disks:
                    storage.disks.append(Disk(**disk))
            for network in result.networks:
                known = {
                    "interface", "ipv4", "ipv6", "gateway", "dns", "vlan",
                    "bond", "mtu", "speed", "duplex", "mac",
                }
                db.add(
                    Network(
                        snapshot_id=snapshot.id,
                        **{k: v for k, v in network.items() if k in known},
                    )
                )
            for vm in result.vms:
                db.add(VM(snapshot_id=snapshot.id, **vm))
            for sensor in result.sensors:
                db.add(Sensor(snapshot_id=snapshot.id, **sensor))
            if result.switch:
                db.add(SwitchInventory(snapshot_id=snapshot.id, **result.switch))
