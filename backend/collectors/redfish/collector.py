"""Redfish collector (HPE iLO first, but standard-schema only).

Uses the DMTF Redfish standard endpoints so any compliant BMC works.
"""
from typing import Any

import httpx

from collectors.base import BaseCollector, CollectorResult, DeviceCredentials
from collectors.errors import RedfishSchemaError
from utils.logging import get_logger

logger = get_logger(__name__)

REDFISH_ROOT: str = "/redfish/v1"


def _threshold(reading: dict, critical_key: str, non_critical_key: str) -> str | None:
    """Prefer the critical threshold, fall back to non-critical."""
    value = reading.get(critical_key)
    if value is None:
        value = reading.get(non_critical_key)
    return str(value) if value is not None else None


class RedfishCollector(BaseCollector):
    name = "redfish"
    collector_type = "REDFISH"

    def applicable(self, creds: DeviceCredentials) -> bool:
        return (
            creds.device_type == "SERVER"
            and bool(creds.ilo_ip)
            and bool(creds.ilo_username)
            and bool(creds.ilo_password)
        )

    async def _collect(self, creds: DeviceCredentials) -> CollectorResult:
        result = CollectorResult(collector_name=self.name)
        base_url = f"https://{creds.ilo_ip}"
        auth = (creds.ilo_username or "", creds.ilo_password or "")

        async with httpx.AsyncClient(
            base_url=base_url, auth=auth, verify=False, timeout=self.timeout_seconds
        ) as client:
            system = await self._first_member(client, f"{REDFISH_ROOT}/Systems")
            if system is None:
                raise RedfishSchemaError("No Redfish ComputerSystem found")
            system_path = str(system["@odata.id"])
            sys_data = await self._get(client, system_path)

            result.system = {
                "manufacturer": sys_data.get("Manufacturer"),
                "model": sys_data.get("Model"),
                "serial": sys_data.get("SerialNumber"),
                "uuid": sys_data.get("UUID"),
                "bios_version": sys_data.get("BiosVersion"),
                "power_state": sys_data.get("PowerState"),
                "health": (sys_data.get("Status") or {}).get("Health"),
            }
            if sys_data.get("BiosVersion"):
                result.firmwares.append(
                    {"component": "BIOS", "version": sys_data["BiosVersion"], "health": "OK"}
                )

            await self._collect_processors(client, sys_data, result)
            await self._collect_memory(client, sys_data, result)
            await self._collect_storage(client, sys_data, result)
            await self._collect_ethernet(client, sys_data, result)
            await self._collect_firmware_inventory(client, result)
            await self._collect_sensors(client, sys_data, result)

        return result

    @staticmethod
    async def _get(client: httpx.AsyncClient, path: str) -> dict[str, Any]:
        response = await client.get(path)
        logger.debug("Redfish GET %s -> %d", path, response.status_code)
        response.raise_for_status()
        return response.json()

    async def _members(self, client: httpx.AsyncClient, path: str) -> list[dict[str, Any]]:
        try:
            data = await self._get(client, path)
        except httpx.HTTPError:
            return []
        return list(data.get("Members") or [])

    async def _first_member(
        self, client: httpx.AsyncClient, path: str
    ) -> dict[str, Any] | None:
        members = await self._members(client, path)
        return members[0] if members else None

    async def _collect_processors(
        self, client: httpx.AsyncClient, sys_data: dict[str, Any], result: CollectorResult
    ) -> None:
        link = (sys_data.get("Processors") or {}).get("@odata.id")
        if not link:
            return
        for member in await self._members(client, link):
            try:
                cpu = await self._get(client, str(member["@odata.id"]))
            except httpx.HTTPError:
                continue
            if (cpu.get("ProcessorType") or "CPU") != "CPU":
                continue
            frequency = cpu.get("MaxSpeedMHz")
            result.cpus.append(
                {
                    "socket": cpu.get("Socket"),
                    "vendor": cpu.get("Manufacturer"),
                    "model": cpu.get("Model"),
                    "cores": cpu.get("TotalCores"),
                    "threads": cpu.get("TotalThreads"),
                    "frequency": f"{frequency} MHz" if frequency else None,
                    "microcode": (cpu.get("ProcessorId") or {}).get("MicrocodeInfo"),
                    "serial": (cpu.get("ProcessorId") or {}).get("IdentificationRegisters"),
                }
            )

    async def _collect_memory(
        self, client: httpx.AsyncClient, sys_data: dict[str, Any], result: CollectorResult
    ) -> None:
        link = (sys_data.get("Memory") or {}).get("@odata.id")
        if not link:
            return
        for member in await self._members(client, link):
            try:
                dimm = await self._get(client, str(member["@odata.id"]))
            except httpx.HTTPError:
                continue
            capacity_mib = dimm.get("CapacityMiB")
            if not capacity_mib:
                continue  # empty slot
            speed = dimm.get("OperatingSpeedMhz")
            result.memories.append(
                {
                    "slot": dimm.get("DeviceLocator") or dimm.get("Id"),
                    "vendor": dimm.get("Manufacturer"),
                    "part_number": (dimm.get("PartNumber") or "").strip() or None,
                    "serial": (dimm.get("SerialNumber") or "").strip() or None,
                    "capacity_gb": int(capacity_mib) // 1024,
                    "speed": f"{speed} MHz" if speed else None,
                    "type": dimm.get("MemoryDeviceType"),
                    "ecc": dimm.get("ErrorCorrection") not in (None, "NoECC"),
                    "status": (dimm.get("Status") or {}).get("Health"),
                }
            )

    async def _collect_storage(
        self, client: httpx.AsyncClient, sys_data: dict[str, Any], result: CollectorResult
    ) -> None:
        link = (sys_data.get("Storage") or {}).get("@odata.id")
        if not link:
            return
        for member in await self._members(client, link):
            try:
                storage = await self._get(client, str(member["@odata.id"]))
            except httpx.HTTPError:
                continue
            controllers = storage.get("StorageControllers") or []
            controller = controllers[0] if controllers else {}
            entry: dict[str, Any] = {
                "controller": controller.get("Model") or storage.get("Name"),
                "vendor": controller.get("Manufacturer"),
                "model": controller.get("Model"),
                "serial": controller.get("SerialNumber"),
                "firmware": controller.get("FirmwareVersion"),
                "health": (storage.get("Status") or {}).get("Health"),
                "disks": [],
            }
            for drive_ref in storage.get("Drives") or []:
                try:
                    drive = await self._get(client, str(drive_ref["@odata.id"]))
                except httpx.HTTPError:
                    continue
                capacity_bytes = drive.get("CapacityBytes")
                capacity_gb = (
                    f"{int(capacity_bytes) // (1024 ** 3)} GB" if capacity_bytes else None
                )
                entry["disks"].append(
                    {
                        "slot": (drive.get("PhysicalLocation") or {})
                        .get("PartLocation", {})
                        .get("ServiceLabel")
                        or drive.get("Id"),
                        "vendor": drive.get("Manufacturer"),
                        "model": drive.get("Model"),
                        "serial": drive.get("SerialNumber"),
                        "capacity": capacity_gb,
                        "firmware": drive.get("Revision"),
                        "health": (drive.get("Status") or {}).get("Health"),
                    }
                )
            result.storages.append(entry)

    async def _collect_ethernet(
        self, client: httpx.AsyncClient, sys_data: dict[str, Any], result: CollectorResult
    ) -> None:
        link = (sys_data.get("EthernetInterfaces") or {}).get("@odata.id")
        if not link:
            return
        for member in await self._members(client, link):
            try:
                nic = await self._get(client, str(member["@odata.id"]))
            except httpx.HTTPError:
                continue
            speed = nic.get("SpeedMbps")
            result.nics.append(
                {
                    "name": nic.get("Name") or nic.get("Id"),
                    "mac": nic.get("MACAddress") or nic.get("PermanentMACAddress"),
                    "speed": f"{speed} Mbps" if speed else None,
                    "link_status": nic.get("LinkStatus"),
                }
            )

    async def _collect_firmware_inventory(
        self, client: httpx.AsyncClient, result: CollectorResult
    ) -> None:
        for member in await self._members(
            client, f"{REDFISH_ROOT}/UpdateService/FirmwareInventory"
        ):
            try:
                item = await self._get(client, str(member["@odata.id"]))
            except httpx.HTTPError:
                continue
            if not item.get("Version"):
                continue
            result.firmwares.append(
                {
                    "component": item.get("Name") or item.get("Id"),
                    "version": item.get("Version"),
                    "release_date": item.get("ReleaseDate"),
                    "health": (item.get("Status") or {}).get("Health") or "OK",
                }
            )

    async def _collect_sensors(
        self, client: httpx.AsyncClient, sys_data: dict[str, Any], result: CollectorResult
    ) -> None:
        chassis_ref = ((sys_data.get("Links") or {}).get("Chassis") or [{}])[0]
        chassis_path = chassis_ref.get("@odata.id")
        if not chassis_path:
            return

        try:
            thermal = await self._get(client, f"{chassis_path}/Thermal")
        except httpx.HTTPError:
            thermal = {}
        for temp in thermal.get("Temperatures") or []:
            if temp.get("ReadingCelsius") is None:
                continue
            result.sensors.append(
                {
                    "type": "Temperature",
                    "name": temp.get("Name"),
                    "value": str(temp.get("ReadingCelsius")),
                    "unit": "°C",
                    "status": (temp.get("Status") or {}).get("Health"),
                    "upper_threshold": _threshold(
                        temp, "UpperThresholdCritical", "UpperThresholdNonCritical"
                    ),
                    "lower_threshold": _threshold(
                        temp, "LowerThresholdCritical", "LowerThresholdNonCritical"
                    ),
                }
            )
        for fan in thermal.get("Fans") or []:
            if fan.get("Reading") is None:
                continue
            result.sensors.append(
                {
                    "type": "Fan",
                    "name": fan.get("Name") or fan.get("FanName"),
                    "value": str(fan.get("Reading")),
                    "unit": fan.get("ReadingUnits") or "RPM",
                    "status": (fan.get("Status") or {}).get("Health"),
                    "upper_threshold": _threshold(
                        fan, "UpperThresholdCritical", "UpperThresholdNonCritical"
                    ),
                    "lower_threshold": _threshold(
                        fan, "LowerThresholdCritical", "LowerThresholdNonCritical"
                    ),
                }
            )

        try:
            power = await self._get(client, f"{chassis_path}/Power")
        except httpx.HTTPError:
            power = {}
        for psu in power.get("PowerSupplies") or []:
            result.sensors.append(
                {
                    "type": "Power",
                    "name": psu.get("Name"),
                    "value": str(psu.get("LastPowerOutputWatts") or ""),
                    "unit": "W",
                    "status": (psu.get("Status") or {}).get("Health"),
                }
            )
            if psu.get("FirmwareVersion"):
                result.firmwares.append(
                    {
                        "component": f"Power Supply {psu.get('Name') or ''}".strip(),
                        "version": psu["FirmwareVersion"],
                        "health": (psu.get("Status") or {}).get("Health") or "OK",
                    }
                )
