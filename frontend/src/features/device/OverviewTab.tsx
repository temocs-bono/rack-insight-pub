import { Cpu, HardDrive, MemoryStick, MonitorPlay, Network, Wrench } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { DeviceDetail, DeviceInventory, SwitchInventory } from "@/types";

function SummaryCard({
  title,
  Icon,
  children,
}: {
  title: string;
  Icon: typeof Cpu;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <Icon className="h-4 w-4 text-blue-600" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-gray-700">{children}</CardContent>
    </Card>
  );
}

function SwitchCard({ sw }: { sw: SwitchInventory }) {
  return (
    <SummaryCard title="Switch" Icon={Network}>
      <p>{sw.model ?? "Unknown model"}</p>
      <p className="text-xs text-gray-500">
        {sw.ios_version ?? "-"} · SN {sw.serial ?? "-"} · Uptime {sw.uptime ?? "-"}
      </p>
    </SummaryCard>
  );
}

export function OverviewTab({
  inventory,
  device,
}: {
  inventory: DeviceInventory;
  device: DeviceDetail;
}) {
  const totalMemory = inventory.memories.reduce(
    (sum, dimm) => sum + (dimm.capacity_gb ?? 0),
    0,
  );
  const runningVMs = inventory.vms.filter((vm) =>
    (vm.state ?? "").toLowerCase().includes("run"),
  ).length;

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      <SummaryCard title="CPU" Icon={Cpu}>
        {inventory.cpus.length > 0 ? (
          <>
            <p>
              {inventory.cpus.length}× {inventory.cpus[0].model ?? "Unknown"}
            </p>
            <p className="text-xs text-gray-500">
              {inventory.cpus.reduce((sum, cpu) => sum + (cpu.cores ?? 0), 0)} cores /{" "}
              {inventory.cpus.reduce((sum, cpu) => sum + (cpu.threads ?? 0), 0)} threads
            </p>
          </>
        ) : (
          <p className="text-gray-400">No data</p>
        )}
      </SummaryCard>
      <SummaryCard title="Memory" Icon={MemoryStick}>
        {inventory.memories.length > 0 ? (
          <>
            <p>
              {totalMemory} GB in {inventory.memories.length} DIMMs
            </p>
            <p className="text-xs text-gray-500">
              {inventory.memories[0].type ?? ""} {inventory.memories[0].speed ?? ""}
            </p>
          </>
        ) : (
          <p className="text-gray-400">No data</p>
        )}
      </SummaryCard>
      <SummaryCard title="NIC" Icon={Network}>
        {inventory.nics.length > 0 ? (
          <p>{inventory.nics.length} interfaces</p>
        ) : (
          <p className="text-gray-400">No data</p>
        )}
      </SummaryCard>
      <SummaryCard title="Firmware" Icon={Wrench}>
        {inventory.firmwares.length > 0 ? (
          <>
            <p>{inventory.firmwares.length} components</p>
            <p className="text-xs text-gray-500">
              BIOS:{" "}
              {inventory.firmwares.find((f) => (f.component ?? "").includes("BIOS"))
                ?.version ?? "-"}
            </p>
          </>
        ) : (
          <p className="text-gray-400">No data</p>
        )}
      </SummaryCard>
      <SummaryCard title="Storage" Icon={HardDrive}>
        {inventory.storages.length > 0 ? (
          <p>
            {inventory.storages.length} controllers ·{" "}
            {inventory.storages.reduce((sum, s) => sum + s.disks.length, 0)} disks
          </p>
        ) : (
          <p className="text-gray-400">No data</p>
        )}
      </SummaryCard>
      {device.device_type === "SWITCH" && inventory.switch ? (
        <SwitchCard sw={inventory.switch} />
      ) : (
        <SummaryCard title="Virtual Machines" Icon={MonitorPlay}>
          {inventory.vms.length > 0 ? (
            <p>
              {inventory.vms.length} VMs ({runningVMs} running)
            </p>
          ) : (
            <p className="text-gray-400">No VMs</p>
          )}
        </SummaryCard>
      )}
    </div>
  );
}
