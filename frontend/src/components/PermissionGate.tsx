import type { ReactNode } from "react";
import { useAuthStore } from "@/stores/auth";

interface PermissionGateProps {
  /** Single permission code, or a list (any-of). */
  permission: string | string[];
  children: ReactNode;
  /** Rendered when the user lacks the permission (default: nothing). */
  fallback?: ReactNode;
}

/**
 * UX-only guard: renders children when the current user holds the permission.
 * The backend remains the authoritative check — this only hides controls the
 * user cannot use (buttons, menu entries, etc.).
 */
export function PermissionGate({ permission, children, fallback = null }: PermissionGateProps) {
  const { hasPermission, hasAnyPermission } = useAuthStore();
  const allowed = Array.isArray(permission)
    ? hasAnyPermission(permission)
    : hasPermission(permission);
  return <>{allowed ? children : fallback}</>;
}
