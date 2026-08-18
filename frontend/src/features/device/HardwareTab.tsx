import { ChevronDown } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import type { DeviceInventory } from "@/types";

function Accordion({
  title,
  count,
  children,
  defaultOpen = false,
}: {
  title: string;
  count: number;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-lg border border-gray-200 bg-white">
      <button
        type="button"
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold"
        onClick={() => setOpen((prev) => !prev)}
      >
        <span>
          {title} <span className="ml-1 font-normal text-gray-400">({count})</span>
        </span>
        <ChevronDown
          className={`h-4 w-4 text-gray-400 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && <div className="border-t border-gray-100 p-3">{children}</div>}
    </div>
  );
}

export function HardwareTab({ inventory }: { inventory: DeviceInventory }) {
  return (
    <div className="flex flex-col gap-3">
      <Accordion title="CPU" count={inventory.cpus.length} defaultOpen>
        <Table>
          <THead>
            <TR>
              <TH>Socket</TH>
              <TH>Model</TH>
              <TH>Cores</TH>
              <TH>Threads</TH>
              <TH>Frequency</TH>
              <TH>Microcode</TH>
            </TR>
          </THead>
          <TBody>
            {inventory.cpus.map((cpu) => (
              <TR key={cpu.id}>
                <TD>{cpu.socket ?? "-"}</TD>
                <TD>{cpu.model ?? "-"}</TD>
                <TD>{cpu.cores ?? "-"}</TD>
                <TD>{cpu.threads ?? "-"}</TD>
                <TD>{cpu.frequency ?? "-"}</TD>
                <TD>{cpu.microcode ?? "-"}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </Accordion>

      <Accordion title="RAM" count={inventory.memories.length}>
        <Table>
          <THead>
            <TR>
              <TH>Slot</TH>
              <TH>Capacity</TH>
              <TH>Type</TH>
              <TH>Speed</TH>
              <TH>Vendor</TH>
              <TH>Part Number</TH>
              <TH>Serial</TH>
              <TH>Status</TH>
            </TR>
          </THead>
          <TBody>
            {inventory.memories.map((dimm) => (
              <TR key={dimm.id}>
                <TD>{dimm.slot ?? "-"}</TD>
                <TD>{dimm.capacity_gb != null ? `${dimm.capacity_gb} GB` : "-"}</TD>
                <TD>{dimm.type ?? "-"}</TD>
                <TD>{dimm.speed ?? "-"}</TD>
                <TD>{dimm.vendor ?? "-"}</TD>
                <TD>{dimm.part_number ?? "-"}</TD>
                <TD>{dimm.serial ?? "-"}</TD>
                <TD>{dimm.status ?? "-"}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </Accordion>

      <Accordion title="NIC" count={inventory.nics.length}>
        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>MAC</TH>
              <TH>Firmware</TH>
              <TH>Driver</TH>
              <TH>Speed</TH>
              <TH>PCI Slot</TH>
              <TH>Link</TH>
            </TR>
          </THead>
          <TBody>
            {inventory.nics.map((nic) => (
              <TR key={nic.id}>
                <TD>{nic.name ?? "-"}</TD>
                <TD className="font-mono text-xs">{nic.mac ?? "-"}</TD>
                <TD>{nic.firmware ?? "-"}</TD>
                <TD>{nic.driver ?? "-"}</TD>
                <TD>{nic.speed ?? "-"}</TD>
                <TD>{nic.pci_slot ?? "-"}</TD>
                <TD>{nic.link_status ?? "-"}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </Accordion>

      <Accordion title="Storage" count={inventory.storages.length}>
        <Table>
          <THead>
            <TR>
              <TH>Controller</TH>
              <TH>RAID</TH>
              <TH>Firmware</TH>
              <TH>Disks</TH>
              <TH>Health</TH>
            </TR>
          </THead>
          <TBody>
            {inventory.storages.map((storage) => (
              <TR key={storage.id}>
                <TD>{storage.controller ?? "-"}</TD>
                <TD>{storage.raid_level ?? "-"}</TD>
                <TD>{storage.firmware ?? "-"}</TD>
                <TD>{storage.disks.length}</TD>
                <TD>{storage.health ?? "-"}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </Accordion>
    </div>
  );
}
