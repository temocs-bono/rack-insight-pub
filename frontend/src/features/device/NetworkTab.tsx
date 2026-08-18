import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import type { NetworkInterface } from "@/types";

export function NetworkTab({ networks }: { networks: NetworkInterface[] }) {
  if (networks.length === 0) {
    return <p className="text-sm text-gray-500">No network data collected yet.</p>;
  }

  const bonds = networks.filter((n) => n.bond);
  const others = networks.filter((n) => !n.bond);
  const ordered = [...bonds, ...others];

  return (
    <Table>
      <THead>
        <TR>
          <TH>Interface</TH>
          <TH>IPv4</TH>
          <TH>IPv6</TH>
          <TH>MAC</TH>
          <TH>Speed</TH>
          <TH>MTU</TH>
          <TH>Gateway</TH>
          <TH>Bond</TH>
          <TH>VLAN</TH>
        </TR>
      </THead>
      <TBody>
        {ordered.map((net) => (
          <TR key={net.id}>
            <TD className={net.bond ? "font-medium" : ""}>{net.interface ?? "-"}</TD>
            <TD className="font-mono text-xs">{net.ipv4 ?? "-"}</TD>
            <TD className="font-mono text-xs">{net.ipv6 ?? "-"}</TD>
            <TD className="font-mono text-xs">{net.mac ?? "-"}</TD>
            <TD>{net.speed ?? "-"}</TD>
            <TD>{net.mtu ?? "-"}</TD>
            <TD>{net.gateway ?? "-"}</TD>
            <TD>{net.bond ?? "-"}</TD>
            <TD>{net.vlan ?? "-"}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
