"""Cisco collector: NX-OS / IOS-XE switch inventory over SSH."""
import re
from typing import Any

from collectors.base import BaseCollector, CollectorResult, DeviceCredentials
from collectors.ssh.client import open_ssh, run_command
from utils.logging import get_logger

logger = get_logger(__name__)


class CiscoCollector(BaseCollector):
    name = "cisco"
    collector_type = "CISCO"

    def applicable(self, creds: DeviceCredentials) -> bool:
        return (
            creds.device_type == "SWITCH"
            and bool(creds.management_ip or creds.hostname)
            and bool(creds.ssh_username)
        )

    async def _collect(self, creds: DeviceCredentials) -> CollectorResult:
        result = CollectorResult(collector_name=self.name)
        conn = await open_ssh(creds, self.timeout_seconds)
        try:
            version_output = await run_command(conn, "show version", self.timeout_seconds)
            inventory_output = await run_command(conn, "show inventory", self.timeout_seconds)
            interfaces_output = await run_command(
                conn, "show ip interface brief", self.timeout_seconds
            )

            result.switch = self._parse_version(version_output, inventory_output)
            result.networks = self._parse_interfaces(interfaces_output)
        finally:
            conn.close()
        return result

    @staticmethod
    def _parse_version(version_output: str, inventory_output: str) -> dict[str, Any]:
        model = None
        serial = None
        inv_match = re.search(
            r'PID:\s*(\S+).*?SN:\s*(\S+)', inventory_output, re.DOTALL
        )
        if inv_match:
            model = inv_match.group(1).rstrip(",")
            serial = inv_match.group(2)

        version = None
        for pattern in (
            r"NXOS:\s*version\s+(\S+)",       # NX-OS
            r"Cisco IOS XE Software.*?Version\s+(\S+)",  # IOS-XE
            r"Version\s+([\w.():]+)",
        ):
            version_match = re.search(pattern, version_output)
            if version_match:
                version = version_match.group(1).rstrip(",")
                break

        uptime_match = re.search(r"uptime is\s+(.+)", version_output)
        return {
            "model": model,
            "ios_version": version,
            "serial": serial,
            "uptime": uptime_match.group(1).strip() if uptime_match else None,
        }

    @staticmethod
    def _parse_interfaces(output: str) -> list[dict[str, Any]]:
        networks: list[dict[str, Any]] = []
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 2 or parts[0].lower() == "interface":
                continue
            ip = parts[1]
            if ip.lower() in ("unassigned", "ip-address"):
                ip = None
            networks.append({"interface": parts[0], "ipv4": ip})
        return networks
