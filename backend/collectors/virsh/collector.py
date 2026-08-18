"""Virsh collector: VM inventory over SSH. Skips cleanly when virsh is absent."""
import re
from typing import Any

from collectors.base import BaseCollector, CollectorResult, DeviceCredentials
from collectors.ssh.client import open_ssh, run_command
from utils.logging import get_logger

logger = get_logger(__name__)


class VirshCollector(BaseCollector):
    name = "virsh"
    collector_type = "SSH"  # virsh runs over the same SSH channel

    def applicable(self, creds: DeviceCredentials) -> bool:
        return (
            creds.device_type == "SERVER"
            and bool(creds.management_ip or creds.hostname)
            and bool(creds.ssh_username)
        )

    async def _collect(self, creds: DeviceCredentials) -> CollectorResult:
        result = CollectorResult(collector_name=self.name)
        conn = await open_ssh(creds, self.timeout_seconds)
        try:
            which = (
                await run_command(conn, "command -v virsh || true", self.timeout_seconds)
            ).strip()
            if not which:
                logger.info("virsh not installed on %s, skipping", creds.hostname)
                result.skipped = True
                return result

            list_output = await run_command(conn, "virsh list --all", self.timeout_seconds)
            for vm_name in self._parse_vm_names(list_output):
                dominfo = await run_command(
                    conn, f"virsh dominfo '{vm_name}'", self.timeout_seconds
                )
                domifaddr = await run_command(
                    conn,
                    f"virsh domifaddr '{vm_name}' 2>/dev/null || true",
                    self.timeout_seconds,
                )
                result.vms.append(self._parse_vm(vm_name, dominfo, domifaddr))
        finally:
            conn.close()
        return result

    @staticmethod
    def _parse_vm_names(list_output: str) -> list[str]:
        names: list[str] = []
        for line in list_output.splitlines():
            match = re.match(r"^\s*(?:\d+|-)\s+(\S+)\s+", line)
            if match:
                names.append(match.group(1))
        return names

    @staticmethod
    def _parse_vm(name: str, dominfo: str, domifaddr: str) -> dict[str, Any]:
        def field(label: str) -> str | None:
            match = re.search(rf"^{label}:\s*(.+)$", dominfo, re.MULTILINE)
            return match.group(1).strip() if match else None

        vcpu_raw = field("CPU\\(s\\)")
        memory_kib = field("Max memory")
        memory = None
        if memory_kib:
            kib_match = re.match(r"(\d+)", memory_kib)
            if kib_match:
                memory = f"{int(kib_match.group(1)) // 1024 // 1024} GB"

        ips = re.findall(r"ipv4\s+(\S+)", domifaddr)
        return {
            "name": name,
            "uuid": field("UUID"),
            "state": field("State"),
            "vcpu": int(vcpu_raw) if vcpu_raw and vcpu_raw.isdigit() else None,
            "memory": memory or memory_kib,
            "os": field("OS Type"),
            "ip": ",".join(ips) if ips else None,
        }
