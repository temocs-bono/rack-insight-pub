"""Shared asyncssh connection helper for SSH-based collectors."""
import asyncssh

from collectors.base import DeviceCredentials


async def open_ssh(creds: DeviceCredentials, timeout_seconds: int) -> asyncssh.SSHClientConnection:
    """Open an SSH connection. Password auth if provided, otherwise key-based
    (client keys / agent resolved by asyncssh)."""
    host = creds.management_ip or creds.hostname
    options: dict = {
        "host": host,
        "username": creds.ssh_username,
        "known_hosts": None,
        "connect_timeout": timeout_seconds,
    }
    if creds.ssh_password:
        options["password"] = creds.ssh_password
    return await asyncssh.connect(**options)


async def run_command(
    conn: asyncssh.SSHClientConnection, command: str, timeout_seconds: int
) -> str:
    result = await conn.run(command, check=False, timeout=timeout_seconds)
    return str(result.stdout or "")
