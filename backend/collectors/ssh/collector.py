"""SSH collector: OS-level data from Linux hosts (Rocky Linux reference)."""
import re
from typing import Any

from collectors.base import BaseCollector, CollectorResult, DeviceCredentials
from collectors.ssh.client import open_ssh, run_command
from utils.logging import get_logger

logger = get_logger(__name__)


class SSHCollector(BaseCollector):
    name = "ssh"
    collector_type = "SSH"

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
            os_release = await run_command(conn, "cat /etc/os-release", self.timeout_seconds)
            kernel = (await run_command(conn, "uname -r", self.timeout_seconds)).strip()
            result.system = {
                "os": self._parse_os_release(os_release),
                "kernel": kernel,
            }

            ip_addr = await run_command(conn, "ip -o addr show", self.timeout_seconds)
            ip_route = await run_command(conn, "ip route show default", self.timeout_seconds)
            dns = await run_command(
                conn, "grep '^nameserver' /etc/resolv.conf || true", self.timeout_seconds
            )
            result.networks = self._parse_networks(ip_addr, ip_route, dns)

            ip_link = await run_command(conn, "ip -o link show", self.timeout_seconds)
            for interface in self._interface_names(ip_link):
                ethtool_out = await run_command(
                    conn, f"ethtool {interface} 2>/dev/null || true", self.timeout_seconds
                )
                driver_out = await run_command(
                    conn, f"ethtool -i {interface} 2>/dev/null || true", self.timeout_seconds
                )
                self._merge_ethtool(result.networks, interface, ethtool_out, driver_out)
        finally:
            conn.close()
        return result

    @staticmethod
    def _parse_os_release(text: str) -> str | None:
        match = re.search(r'^PRETTY_NAME="?([^"\n]+)"?', text, re.MULTILINE)
        return match.group(1) if match else None

    @staticmethod
    def _interface_names(ip_link_output: str) -> list[str]:
        names: list[str] = []
        for line in ip_link_output.splitlines():
            match = re.match(r"^\d+:\s+([^:@\s]+)", line)
            if match and match.group(1) != "lo":
                names.append(match.group(1))
        return names

    @staticmethod
    def _parse_networks(ip_addr: str, ip_route: str, dns_output: str) -> list[dict[str, Any]]:
        gateway_match = re.search(r"default via (\S+)", ip_route)
        gateway = gateway_match.group(1) if gateway_match else None
        dns_servers = ",".join(re.findall(r"^nameserver\s+(\S+)", dns_output, re.MULTILINE))

        interfaces: dict[str, dict[str, Any]] = {}
        for line in ip_addr.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            name = parts[1]
            if name == "lo":
                continue
            entry = interfaces.setdefault(
                name,
                {
                    "interface": name,
                    "ipv4": None,
                    "ipv6": None,
                    "gateway": gateway,
                    "dns": dns_servers or None,
                    "bond": "bond" if name.startswith("bond") else None,
                    "vlan": name.split(".", 1)[1] if "." in name else None,
                },
            )
            if parts[2] == "inet" and entry["ipv4"] is None:
                entry["ipv4"] = parts[3]
            elif parts[2] == "inet6" and entry["ipv6"] is None and not parts[3].startswith("fe80"):
                entry["ipv6"] = parts[3]
        return list(interfaces.values())

    @staticmethod
    def _merge_ethtool(
        networks: list[dict[str, Any]], interface: str, ethtool_out: str, driver_out: str
    ) -> None:
        speed_match = re.search(r"Speed:\s*(\S+)", ethtool_out)
        duplex_match = re.search(r"Duplex:\s*(\S+)", ethtool_out)
        driver_match = re.search(r"^driver:\s*(\S+)", driver_out, re.MULTILINE)
        for entry in networks:
            if entry["interface"] == interface:
                if speed_match and speed_match.group(1) != "Unknown!":
                    entry["speed"] = speed_match.group(1)
                if duplex_match:
                    entry["duplex"] = duplex_match.group(1)
                if driver_match:
                    entry["driver"] = driver_match.group(1)
                return
