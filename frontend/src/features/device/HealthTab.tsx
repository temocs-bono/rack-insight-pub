import {
  Fan,
  HardDrive,
  HeartPulse,
  MemoryStick,
  Network,
  Thermometer,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { HealthSummaryCard } from "@/components/HealthSummaryCard";
import { StatusPill, normalizeStatus } from "@/components/StatusPill";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { SensorTab } from "@/features/device/SensorTab";
import { useDeviceHealth } from "@/hooks/queries";
import type { Sensor } from "@/types";

const GROUP_META: Record<string, { label: string; Icon: LucideIcon }> = {
  temperature: { label: "Temperature", Icon: Thermometer },
  power: { label: "Power", Icon: Zap },
  fan: { label: "Fan", Icon: Fan },
  other: { label: "Other Sensors", Icon: HeartPulse },
};

function HealthTimeline({
  timeline,
}: {
  timeline: { collected_at: string; score: number; label: string }[];
}) {
  if (timeline.length === 0) {
    return <p className="text-sm text-gray-400">No collections yet.</p>;
  }
  const max = 100;
  return (
    <div className="flex items-end gap-1.5">
      {timeline.map((point) => {
        const tone =
          point.label === "Healthy"
            ? "bg-green-500"
            : point.label === "Warning"
              ? "bg-orange-400"
              : "bg-red-500";
        return (
          <div
            key={point.collected_at}
            className="flex flex-col items-center gap-1"
            title={`${new Date(point.collected_at).toLocaleString()} — ${point.score} (${point.label})`}
          >
            <div className="flex h-24 w-6 items-end rounded bg-gray-100">
              <div
                className={`w-full rounded ${tone}`}
                style={{ height: `${Math.max(6, (point.score / max) * 100)}%` }}
              />
            </div>
            <span className="text-[10px] text-gray-400">
              {new Date(point.collected_at).toLocaleDateString(undefined, {
                month: "numeric",
                day: "numeric",
              })}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Health tab (1.3.0): overall health, sensor summary, sensor cards and the
 *  health timeline. Health is separate from inventory — sensor readings live
 *  here and never create hardware-change alerts. */
export function HealthTab({ deviceId, sensors }: { deviceId: string; sensors: Sensor[] }) {
  const { data: health, isLoading } = useDeviceHealth(deviceId);

  if (isLoading || !health) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-4 p-4">
          <HeartPulse className="h-9 w-9 text-blue-500" />
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">
              Overall Health
            </p>
            <div className="flex items-center gap-2">
              <StatusPill
                status={normalizeStatus(health.overall_label)}
                text={
                  health.overall_score !== null
                    ? `${health.overall_score} · ${health.overall_label}`
                    : health.overall_label
                }
              />
            </div>
          </div>
          <div className="ml-auto text-right text-xs text-gray-400">
            Last collection:{" "}
            {health.last_collected_at
              ? new Date(health.last_collected_at).toLocaleString()
              : "Never"}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {health.sensor_groups.map((group) => {
          const meta = GROUP_META[group.group] ?? GROUP_META.other;
          return (
            <HealthSummaryCard
              key={group.group}
              title={meta.label}
              Icon={meta.Icon}
              label={group.label}
              detail={`${group.ok}/${group.total} sensors OK`}
            />
          );
        })}
        <HealthSummaryCard title="Storage" Icon={HardDrive} label={health.storage_label} />
        <HealthSummaryCard title="Memory" Icon={MemoryStick} label={health.memory_label} />
        <HealthSummaryCard title="Network" Icon={Network} label={health.network_label} />
      </div>

      <Card>
        <CardContent className="p-4">
          <h3 className="mb-3 text-sm font-semibold text-gray-900">Health Timeline</h3>
          <HealthTimeline timeline={health.timeline} />
        </CardContent>
      </Card>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-gray-900">Sensors</h3>
        <SensorTab sensors={sensors} />
      </div>
    </div>
  );
}
