import { ArrowRight, MinusCircle, PlusCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { ChangeItem } from "@/types";

/**
 * Visual before -> after view of hardware/firmware changes. Reused by the
 * Alert Center (alert changes) and Device History entries.
 */
export function DiffViewer({ changes }: { changes: ChangeItem[] }) {
  if (changes.length === 0) {
    return <p className="text-sm text-gray-400">No change details recorded.</p>;
  }
  return (
    <div className="flex flex-col gap-1.5">
      {changes.map((change, index) => (
        <div
          key={`${change.section}-${change.identifier}-${change.field ?? ""}-${index}`}
          className="flex flex-wrap items-center gap-2 rounded-md border border-gray-100 bg-gray-50 px-2.5 py-1.5 text-sm"
        >
          <Badge variant="muted">{change.section}</Badge>
          <span className="font-medium text-gray-800">{change.identifier}</span>
          {change.field && <span className="text-xs text-gray-400">{change.field}</span>}
          {change.change === "added" && (
            <span className="flex items-center gap-1 text-green-700">
              <PlusCircle className="h-3.5 w-3.5" /> added
            </span>
          )}
          {change.change === "removed" && (
            <span className="flex items-center gap-1 text-red-700">
              <MinusCircle className="h-3.5 w-3.5" /> removed
            </span>
          )}
          {change.change === "changed" && (
            <span className="flex items-center gap-1.5">
              <code className="rounded bg-red-50 px-1.5 py-0.5 text-xs text-red-700 line-through">
                {change.old ?? "-"}
              </code>
              <ArrowRight className="h-3.5 w-3.5 text-gray-400" />
              <code className="rounded bg-green-50 px-1.5 py-0.5 text-xs font-medium text-green-700">
                {change.new ?? "-"}
              </code>
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
