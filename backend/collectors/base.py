"""Collector plugin contract.

Every collector is independent: it receives device connection info, returns a
CollectorResult, and must never raise out of `collect()` (failures are captured
in the result). New vendors are added as new plugins without touching others.
"""
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from collectors.errors import ClassifiedError, classify_error
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DeviceCredentials:
    """Decrypted connection info handed to collectors. Never logged."""

    hostname: str
    device_type: str
    management_ip: str | None = None
    ilo_ip: str | None = None
    ilo_username: str | None = None
    ilo_password: str | None = None
    ssh_username: str | None = None
    ssh_password: str | None = None
    snmp_community: str | None = None
    # Explicit collector selection from Device.collector_types; None means auto.
    collector_types: frozenset[str] | None = None


@dataclass
class CollectorResult:
    """Normalized output merged by the CollectorManager into a Snapshot."""

    collector_name: str
    success: bool = False
    skipped: bool = False
    error: str | None = None
    error_code: str | None = None
    readable_message: str | None = None
    duration_ms: int = 0
    system: dict[str, Any] = field(default_factory=dict)
    cpus: list[dict[str, Any]] = field(default_factory=list)
    memories: list[dict[str, Any]] = field(default_factory=list)
    nics: list[dict[str, Any]] = field(default_factory=list)
    firmwares: list[dict[str, Any]] = field(default_factory=list)
    storages: list[dict[str, Any]] = field(default_factory=list)
    networks: list[dict[str, Any]] = field(default_factory=list)
    vms: list[dict[str, Any]] = field(default_factory=list)
    sensors: list[dict[str, Any]] = field(default_factory=list)
    switch: dict[str, Any] | None = None


class BaseCollector(ABC):
    """Abstract collector with retry + timing built in."""

    name: str = "base"
    # Which Device.collector_types entry enables this collector (None = always).
    collector_type: str | None = None

    def __init__(self, timeout_seconds: int, retry_count: int) -> None:
        self.timeout_seconds = timeout_seconds
        self.retry_count = retry_count

    def type_enabled(self, creds: DeviceCredentials) -> bool:
        """Honor the device's explicit collector type selection, if any."""
        if creds.collector_types is None or self.collector_type is None:
            return True
        return self.collector_type in creds.collector_types

    def applicable(self, creds: DeviceCredentials) -> bool:
        """Whether this collector can run for the given device."""
        return True

    @abstractmethod
    async def _collect(self, creds: DeviceCredentials) -> CollectorResult:
        """Vendor-specific collection. May raise; caller handles retries."""

    async def collect(self, creds: DeviceCredentials) -> CollectorResult:
        """Run collection with retries. Never raises."""
        if not self.type_enabled(creds) or not self.applicable(creds):
            logger.info("Collector %s skipped for %s (not applicable)", self.name, creds.hostname)
            return CollectorResult(collector_name=self.name, skipped=True)

        started = time.monotonic()
        last_error: ClassifiedError | None = None
        for attempt in range(1, self.retry_count + 1):
            try:
                logger.info(
                    "Collector %s start host=%s attempt=%d/%d",
                    self.name, creds.hostname, attempt, self.retry_count,
                )
                result = await self._collect(creds)
                result.duration_ms = int((time.monotonic() - started) * 1000)
                result.success = True
                logger.info(
                    "Collector %s finish host=%s duration_ms=%d",
                    self.name, creds.hostname, result.duration_ms,
                )
                return result
            except Exception as exc:
                last_error = classify_error(exc)
                logger.warning(
                    "Collector %s failed host=%s attempt=%d/%d code=%s: %s",
                    self.name, creds.hostname, attempt, self.retry_count,
                    last_error.code, exc,
                )

        return CollectorResult(
            collector_name=self.name,
            success=False,
            error=last_error.detail if last_error else None,
            error_code=last_error.code if last_error else None,
            readable_message=last_error.readable_message if last_error else None,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
