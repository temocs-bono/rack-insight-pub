import { useQuery } from "@tanstack/react-query";
import { ScrollText } from "lucide-react";
import { useState } from "react";
import { Breadcrumb } from "@/components/Breadcrumb";
import { EmptyState } from "@/components/EmptyState";
import { HistoryCard, historyKindIcon } from "@/components/HistoryCard";
import { Timeline } from "@/components/Timeline";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/services/api";

const KINDS = [
  { value: "firmware_change", label: "Firmware changes" },
  { value: "hardware_change", label: "Hardware changes" },
  { value: "collector_failure", label: "Collector failures" },
  { value: "manual_resolve", label: "Manual resolves" },
  { value: "device_recovered", label: "Recoveries" },
];

const PAGE_SIZE = 25;

export function HistoryPage() {
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["history", kind, q, page],
    queryFn: () => api.history({ kind, q, page, page_size: PAGE_SIZE }),
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="flex flex-col gap-4">
      <Breadcrumb crumbs={[{ label: "Alerts" }, { label: "History" }]} />
      <p className="text-sm text-gray-500">
        Permanent, immutable record of every meaningful change: firmware upgrades, hardware
        replacements, collector failures and manual resolves. History never disappears.
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <Select
          className="w-56"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All record types</option>
          {KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </Select>
        <Input
          className="w-72"
          placeholder="Search hostname or description…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
        />
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          Icon={ScrollText}
          title="No history yet"
          description="History entries are recorded automatically as devices change over time."
        />
      ) : (
        <>
          <Timeline
            items={data.items.map((entry) => ({
              id: entry.id,
              icon: historyKindIcon(entry.kind),
              timestamp: entry.created_at,
              content: <HistoryCard entry={entry} showHostname />,
            }))}
          />
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>
              {data.total} record{data.total !== 1 ? "s" : ""}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <span>
                Page {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
