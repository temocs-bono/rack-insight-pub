import { Badge } from "@/components/ui/badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import type { VM } from "@/types";

export function VMTab({ vms }: { vms: VM[] }) {
  if (vms.length === 0) {
    return (
      <p className="text-sm text-gray-500">
        No virtual machines found (virsh not installed or no VMs defined).
      </p>
    );
  }

  return (
    <Table>
      <THead>
        <TR>
          <TH>Name</TH>
          <TH>State</TH>
          <TH>vCPU</TH>
          <TH>Memory</TH>
          <TH>OS</TH>
          <TH>Kernel</TH>
          <TH>IP</TH>
        </TR>
      </THead>
      <TBody>
        {vms.map((vm) => (
          <TR key={vm.id}>
            <TD className="font-medium">{vm.name ?? "-"}</TD>
            <TD>
              <Badge
                variant={
                  (vm.state ?? "").toLowerCase().includes("run") ? "success" : "muted"
                }
              >
                {vm.state ?? "unknown"}
              </Badge>
            </TD>
            <TD>{vm.vcpu ?? "-"}</TD>
            <TD>{vm.memory ?? "-"}</TD>
            <TD>{vm.os ?? "-"}</TD>
            <TD>{vm.kernel ?? "-"}</TD>
            <TD className="font-mono text-xs">{vm.ip ?? "-"}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
