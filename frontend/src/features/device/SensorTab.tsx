import { StatusPill, normalizeStatus } from "@/components/StatusPill";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import type { Sensor } from "@/types";

export function SensorTab({ sensors }: { sensors: Sensor[] }) {
  if (sensors.length === 0) {
    return <p className="text-sm text-gray-500">No sensor data collected yet.</p>;
  }

  return (
    <Table>
      <THead>
        <TR>
          <TH>Type</TH>
          <TH>Name</TH>
          <TH>Value</TH>
          <TH>Thresholds</TH>
          <TH>Status</TH>
        </TR>
      </THead>
      <TBody>
        {sensors.map((sensor) => (
          <TR key={sensor.id}>
            <TD>{sensor.type ?? "-"}</TD>
            <TD>{sensor.name ?? "-"}</TD>
            <TD>
              {sensor.value ?? "-"} {sensor.unit ?? ""}
            </TD>
            <TD className="text-xs text-gray-500">
              {sensor.upper_threshold || sensor.lower_threshold ? (
                <>
                  {sensor.lower_threshold != null && `min ${sensor.lower_threshold}`}
                  {sensor.lower_threshold != null && sensor.upper_threshold != null && " / "}
                  {sensor.upper_threshold != null && `max ${sensor.upper_threshold}`}
                  {sensor.unit ? ` ${sensor.unit}` : ""}
                </>
              ) : (
                <span className="text-gray-400">Threshold unavailable</span>
              )}
            </TD>
            <TD>
              <StatusPill
                status={normalizeStatus(sensor.status)}
                text={sensor.status ?? "Unknown"}
              />
            </TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
