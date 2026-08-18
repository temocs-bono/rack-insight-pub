import { StatusPill, normalizeStatus } from "@/components/StatusPill";
import { Badge } from "@/components/ui/badge";

export function HealthBadge({
  score,
  label,
}: {
  score: number | null;
  label: string | null;
}) {
  if (score === null || label === null) {
    return <Badge variant="muted">No health data</Badge>;
  }
  return <StatusPill status={normalizeStatus(label)} text={`${score} · ${label}`} />;
}
