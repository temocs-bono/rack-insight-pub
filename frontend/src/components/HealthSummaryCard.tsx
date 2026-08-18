import type { LucideIcon } from "lucide-react";
import { StatusPill, normalizeStatus } from "@/components/StatusPill";
import { Card, CardContent } from "@/components/ui/card";
import type { HealthLabel } from "@/types";

/** Compact health tile: icon, title, Healthy/Warning/Critical/Unknown pill. */
export function HealthSummaryCard({
  title,
  Icon,
  label,
  detail,
}: {
  title: string;
  Icon: LucideIcon;
  label: HealthLabel | string;
  detail?: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <Icon className="h-7 w-7 text-blue-500" />
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">
            {title}
          </p>
          <StatusPill status={normalizeStatus(label)} text={label} />
          {detail && <p className="mt-0.5 truncate text-xs text-gray-500">{detail}</p>}
        </div>
      </CardContent>
    </Card>
  );
}
