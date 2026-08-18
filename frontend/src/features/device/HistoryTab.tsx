import { ScrollText } from "lucide-react";
import { EmptyState } from "@/components/EmptyState";
import { HistoryCard, historyKindIcon } from "@/components/HistoryCard";
import { Timeline } from "@/components/Timeline";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeviceHistory } from "@/hooks/queries";

/** History tab (1.3.0): the device's complete, immutable change timeline —
 *  firmware upgrades, hardware replacements, collector failures, resolves. */
export function HistoryTab({ deviceId }: { deviceId: string }) {
  const { data, isLoading } = useDeviceHistory(deviceId);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <EmptyState
        Icon={ScrollText}
        title="No history yet"
        description="Changes to this device (firmware, hardware, failures, resolves) will be recorded here permanently."
      />
    );
  }

  return (
    <Timeline
      items={data.items.map((entry) => ({
        id: entry.id,
        icon: historyKindIcon(entry.kind),
        timestamp: entry.created_at,
        content: <HistoryCard entry={entry} />,
      }))}
    />
  );
}
