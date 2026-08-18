import { HardDrive } from "lucide-react";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import type { Disk, Storage } from "@/types";

export function StorageTab({ storages }: { storages: Storage[] }) {
  const [selectedDisk, setSelectedDisk] = useState<Disk | null>(null);

  if (storages.length === 0) {
    return <p className="text-sm text-gray-500">No storage data collected yet.</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      {storages.map((storage) => (
        <Card key={storage.id}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <HardDrive className="h-4 w-4 text-blue-600" />
              {storage.controller ?? "Storage Controller"}
              <span className="ml-2 text-xs font-normal text-gray-500">
                {storage.raid_level ? `RAID ${storage.raid_level} · ` : ""}
                FW {storage.firmware ?? "-"} · {storage.health ?? "Unknown"}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <THead>
                <TR>
                  <TH>Slot</TH>
                  <TH>Model</TH>
                  <TH>Capacity</TH>
                  <TH>Firmware</TH>
                  <TH>Health</TH>
                </TR>
              </THead>
              <TBody>
                {storage.disks.map((disk) => (
                  <TR
                    key={disk.id}
                    className="cursor-pointer"
                    onClick={() =>
                      setSelectedDisk(selectedDisk?.id === disk.id ? null : disk)
                    }
                  >
                    <TD>{disk.slot ?? "-"}</TD>
                    <TD>{disk.model ?? "-"}</TD>
                    <TD>{disk.capacity ?? "-"}</TD>
                    <TD>{disk.firmware ?? "-"}</TD>
                    <TD>{disk.health ?? "-"}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            {selectedDisk && storage.disks.some((d) => d.id === selectedDisk.id) && (
              <div className="mt-3 rounded-md border border-blue-200 bg-blue-50 p-3 text-xs text-gray-700">
                <p className="mb-1 font-semibold">Disk detail — {selectedDisk.slot}</p>
                <p>Vendor: {selectedDisk.vendor ?? "-"}</p>
                <p>Model: {selectedDisk.model ?? "-"}</p>
                <p>Serial: {selectedDisk.serial ?? "-"}</p>
                <p>Capacity: {selectedDisk.capacity ?? "-"}</p>
                <p>Firmware: {selectedDisk.firmware ?? "-"}</p>
                <p>Health: {selectedDisk.health ?? "-"}</p>
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
