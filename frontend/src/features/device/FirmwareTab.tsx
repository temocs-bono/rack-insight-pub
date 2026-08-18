import { useMemo } from "react";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import type { Firmware } from "@/types";

export function FirmwareTab({ firmwares }: { firmwares: Firmware[] }) {
  // Components whose version differs across identically named entries are
  // highlighted in orange per the firmware-diff UI rule.
  const mismatched = useMemo(() => {
    const versionsByComponent = new Map<string, Set<string>>();
    for (const fw of firmwares) {
      if (!fw.component || !fw.version) continue;
      const set = versionsByComponent.get(fw.component) ?? new Set<string>();
      set.add(fw.version);
      versionsByComponent.set(fw.component, set);
    }
    return new Set(
      [...versionsByComponent.entries()]
        .filter(([, versions]) => versions.size > 1)
        .map(([component]) => component),
    );
  }, [firmwares]);

  if (firmwares.length === 0) {
    return <p className="text-sm text-gray-500">No firmware data collected yet.</p>;
  }

  return (
    <Table>
      <THead>
        <TR>
          <TH>Component</TH>
          <TH>Current Version</TH>
          <TH>Release Date</TH>
          <TH>Health</TH>
        </TR>
      </THead>
      <TBody>
        {firmwares.map((fw) => (
          <TR key={fw.id}>
            <TD>{fw.component ?? "-"}</TD>
            <TD
              className={
                fw.component && mismatched.has(fw.component)
                  ? "font-medium text-orange-600"
                  : ""
              }
            >
              {fw.version ?? "-"}
            </TD>
            <TD>{fw.release_date ?? "-"}</TD>
            <TD>{fw.health ?? "-"}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
