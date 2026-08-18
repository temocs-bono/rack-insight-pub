import {
  CheckCircle2,
  Cpu,
  RotateCcw,
  UserCheck,
  Wrench,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { DiffViewer } from "@/components/DiffViewer";
import { Badge } from "@/components/ui/badge";
import type { HistoryEntry } from "@/types";

const KIND_META: Record<string, { label: string; Icon: LucideIcon; tone: string }> = {
  firmware_change: { label: "Firmware", Icon: Wrench, tone: "text-blue-600" },
  hardware_change: { label: "Hardware", Icon: Cpu, tone: "text-orange-600" },
  collector_failure: { label: "Collection", Icon: XCircle, tone: "text-red-600" },
  manual_resolve: { label: "Resolve", Icon: UserCheck, tone: "text-green-700" },
  device_recovered: { label: "Recovery", Icon: RotateCcw, tone: "text-green-600" },
};

export function historyKindIcon(kind: string) {
  const meta = KIND_META[kind] ?? {
    label: kind,
    Icon: CheckCircle2,
    tone: "text-gray-500",
  };
  return <meta.Icon className={`h-3 w-3 ${meta.tone}`} />;
}

/** One immutable device-history record with its change diff. */
export function HistoryCard({
  entry,
  showHostname = false,
}: {
  entry: HistoryEntry;
  showHostname?: boolean;
}) {
  const meta = KIND_META[entry.kind] ?? {
    label: entry.kind,
    Icon: CheckCircle2,
    tone: "text-gray-500",
  };
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <Badge variant="muted">
          <meta.Icon className={`h-3 w-3 ${meta.tone}`} /> {meta.label}
        </Badge>
        {showHostname && entry.hostname && (
          <Link
            to={`/devices/${entry.device_id}`}
            className="text-sm font-medium text-blue-700 hover:underline"
          >
            {entry.hostname}
          </Link>
        )}
        <span className="text-sm text-gray-800">{entry.title}</span>
      </div>
      {entry.changes.length > 0 && (
        <div className="mt-2">
          <DiffViewer changes={entry.changes} />
        </div>
      )}
    </div>
  );
}
