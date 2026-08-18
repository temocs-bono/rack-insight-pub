import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  RefreshCw,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { Badge, type BadgeProps } from "@/components/ui/badge";

/** Single source of truth for status/health visual language (F3).
 *  Healthy/Online = green, Warning = orange, Critical/Offline = red,
 *  Unknown = gray, Refreshing = blue. Icon + text always together. */
export type UnifiedStatus =
  | "HEALTHY"
  | "ONLINE"
  | "WARNING"
  | "CRITICAL"
  | "OFFLINE"
  | "UNKNOWN"
  | "REFRESHING";

interface StatusStyle {
  label: string;
  variant: NonNullable<BadgeProps["variant"]>;
  Icon: LucideIcon;
  spin?: boolean;
}

export const STATUS_STYLES: Record<UnifiedStatus, StatusStyle> = {
  HEALTHY: { label: "Healthy", variant: "success", Icon: CheckCircle2 },
  ONLINE: { label: "Online", variant: "success", Icon: CheckCircle2 },
  WARNING: { label: "Warning", variant: "warning", Icon: AlertTriangle },
  CRITICAL: { label: "Critical", variant: "critical", Icon: Activity },
  OFFLINE: { label: "Offline", variant: "critical", Icon: XCircle },
  UNKNOWN: { label: "Unknown", variant: "muted", Icon: HelpCircle },
  REFRESHING: { label: "Refreshing", variant: "default", Icon: RefreshCw, spin: true },
};

export function normalizeStatus(value: string | null | undefined): UnifiedStatus {
  const upper = (value ?? "").toUpperCase();
  if (upper in STATUS_STYLES) return upper as UnifiedStatus;
  if (["OK", "GOOD", "NORMAL", "ENABLED", "RUNNING"].includes(upper)) return "HEALTHY";
  if (upper === "") return "UNKNOWN";
  return "WARNING";
}

export function StatusPill({
  status,
  text,
}: {
  status: UnifiedStatus;
  text?: string;
}) {
  const { label, variant, Icon, spin } = STATUS_STYLES[status];
  return (
    <Badge variant={variant}>
      <Icon className={spin ? "h-3 w-3 animate-spin" : "h-3 w-3"} />
      {text ?? label}
    </Badge>
  );
}
