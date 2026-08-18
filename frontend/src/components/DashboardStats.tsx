import { Activity, AlertTriangle, CheckCircle2, Server, XCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboardSummary } from "@/hooks/queries";
import type { DashboardSummary } from "@/types";

const CARDS: {
  key: keyof DashboardSummary;
  label: string;
  Icon: typeof Server;
  accent: string;
}[] = [
  { key: "total_devices", label: "Total Devices", Icon: Server, accent: "text-blue-600" },
  { key: "online", label: "Online", Icon: CheckCircle2, accent: "text-green-600" },
  { key: "warning", label: "Warning", Icon: AlertTriangle, accent: "text-orange-600" },
  { key: "critical", label: "Critical", Icon: Activity, accent: "text-red-600" },
  { key: "offline", label: "Offline", Icon: XCircle, accent: "text-red-600" },
];

export function DashboardStats() {
  const { data: summary, isLoading } = useDashboardSummary();

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {CARDS.map((card) => (
          <Skeleton key={card.key} className="h-20" />
        ))}
      </div>
    );
  }
  if (!summary) return null;

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      {CARDS.map(({ key, label, Icon, accent }) => (
        <Card key={key}>
          <CardContent className="flex items-center gap-3 p-4">
            <Icon className={`h-6 w-6 shrink-0 ${accent}`} />
            <div>
              <p className="text-2xl font-semibold leading-none">{summary[key]}</p>
              <p className="mt-1 text-xs uppercase tracking-wide text-gray-500">{label}</p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
