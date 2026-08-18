import { AlertTriangle, CheckCircle2, Info, OctagonAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { AlertSeverity, AlertStatus } from "@/types";

export function AlertSeverityBadge({ severity }: { severity: AlertSeverity }) {
  if (severity === "CRITICAL") {
    return (
      <Badge variant="critical">
        <OctagonAlert className="h-3 w-3" /> Critical
      </Badge>
    );
  }
  if (severity === "WARNING") {
    return (
      <Badge variant="warning">
        <AlertTriangle className="h-3 w-3" /> Warning
      </Badge>
    );
  }
  return (
    <Badge variant="default">
      <Info className="h-3 w-3" /> Info
    </Badge>
  );
}

export function AlertStatusBadge({ status }: { status: AlertStatus }) {
  if (status === "RESOLVED") {
    return (
      <Badge variant="success">
        <CheckCircle2 className="h-3 w-3" /> Resolved
      </Badge>
    );
  }
  return <Badge variant="critical">Active</Badge>;
}
