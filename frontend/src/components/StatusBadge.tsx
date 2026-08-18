import { StatusPill, type UnifiedStatus } from "@/components/StatusPill";
import type { DeviceStatus } from "@/types";

export function StatusBadge({ status }: { status: DeviceStatus | "REFRESHING" }) {
  return <StatusPill status={status as UnifiedStatus} />;
}
