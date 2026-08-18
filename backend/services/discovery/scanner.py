"""SNMP scanner abstraction (F1).

`SnmpScanner` performs a real SNMP GET of the standard system OIDs using
pysnmp, which is imported lazily so the application runs (and is testable)
without SNMP support installed. Tests inject a fake scanner implementing the
`DiscoveryScanner` protocol.
"""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from utils.logging import get_logger

logger = get_logger(__name__)

# Standard SNMPv2-MIB system OIDs.
OID_SYSDESCR = "1.3.6.1.2.1.1.1.0"
OID_SYSOBJECTID = "1.3.6.1.2.1.1.2.0"
OID_SYSNAME = "1.3.6.1.2.1.1.5.0"

_VENDOR_KEYWORDS = {
    "cisco": "Cisco",
    "hewlett": "HPE",
    "hpe": "HPE",
    "hp ": "HPE",
    "proliant": "HPE",
    "dell": "Dell",
    "juniper": "Juniper",
    "arista": "Arista",
    "mellanox": "Mellanox",
    "supermicro": "Supermicro",
}


class DiscoveryUnavailable(RuntimeError):
    """Raised when SNMP support (pysnmp) is not installed."""


@dataclass
class SnmpProbeResult:
    ip_address: str
    reachable: bool
    sysname: str | None = None
    sysdescr: str | None = None
    sysobjectid: str | None = None


@runtime_checkable
class DiscoveryScanner(Protocol):
    async def probe(
        self, ip_address: str, community: str, timeout: float
    ) -> SnmpProbeResult: ...


def infer_vendor(sysdescr: str | None) -> str | None:
    if not sysdescr:
        return None
    lowered = sysdescr.lower()
    for keyword, vendor in _VENDOR_KEYWORDS.items():
        if keyword in lowered:
            return vendor
    return None


def infer_device_type(sysdescr: str | None) -> str | None:
    """Best-effort classification into SERVER / SWITCH (mapped to Device types)."""
    if not sysdescr:
        return None
    lowered = sysdescr.lower()
    if any(k in lowered for k in ("switch", "nexus", "catalyst", "ios", "nx-os", "arista")):
        return "SWITCH"
    if any(k in lowered for k in ("router", "routing")):
        return "SWITCH"  # routers are managed as network devices (SWITCH type)
    if any(k in lowered for k in ("server", "proliant", "poweredge", "ilo", "idrac", "linux")):
        return "SERVER"
    return None


class SnmpScanner:
    """Real SNMP scanner backed by pysnmp (imported lazily)."""

    async def probe(
        self, ip_address: str, community: str, timeout: float
    ) -> SnmpProbeResult:
        try:
            from pysnmp.hlapi.asyncio import (  # type: ignore
                CommunityData,
                ContextData,
                ObjectIdentity,
                ObjectType,
                SnmpEngine,
                UdpTransportTarget,
                getCmd,
            )
        except Exception as exc:  # pragma: no cover - depends on optional dep
            raise DiscoveryUnavailable(
                "SNMP support is not installed (pysnmp missing)"
            ) from exc

        try:
            error_indication, error_status, _, var_binds = await getCmd(
                SnmpEngine(),
                CommunityData(community, mpModel=1),
                UdpTransportTarget((ip_address, 161), timeout=timeout, retries=1),
                ContextData(),
                ObjectType(ObjectIdentity(OID_SYSDESCR)),
                ObjectType(ObjectIdentity(OID_SYSOBJECTID)),
                ObjectType(ObjectIdentity(OID_SYSNAME)),
            )
        except Exception as exc:  # pragma: no cover - network dependent
            logger.debug("SNMP probe error for %s: %s", ip_address, exc)
            return SnmpProbeResult(ip_address=ip_address, reachable=False)

        if error_indication or error_status:
            return SnmpProbeResult(ip_address=ip_address, reachable=False)

        values = [str(vb[1]) for vb in var_binds]
        sysdescr = values[0] if len(values) > 0 else None
        sysobjectid = values[1] if len(values) > 1 else None
        sysname = values[2] if len(values) > 2 else None
        return SnmpProbeResult(
            ip_address=ip_address,
            reachable=True,
            sysname=sysname or None,
            sysdescr=sysdescr or None,
            sysobjectid=sysobjectid or None,
        )
