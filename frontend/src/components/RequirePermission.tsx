import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { ShieldAlert } from "lucide-react";
import { EmptyState } from "@/components/EmptyState";
import { useAuthStore } from "@/stores/auth";

interface RequirePermissionProps {
  /** Single permission code, or a list (any-of). */
  permission: string | string[];
  children: ReactNode;
  /** Where to send unauthenticated users (default: /login). */
  redirectTo?: string;
}

/**
 * Route-level guard. Unauthenticated users are redirected to login;
 * authenticated users without the permission see an access-denied panel
 * (the backend still enforces authorization on every request).
 */
export function RequirePermission({
  permission,
  children,
  redirectTo = "/login",
}: RequirePermissionProps) {
  const { accessToken, hasPermission, hasAnyPermission } = useAuthStore();
  if (!accessToken) return <Navigate to={redirectTo} replace />;

  const allowed = Array.isArray(permission)
    ? hasAnyPermission(permission)
    : hasPermission(permission);

  if (!allowed) {
    return (
      <EmptyState
        Icon={ShieldAlert}
        title="Access denied"
        description="You do not have permission to view this page. Contact an administrator if you believe this is a mistake."
      />
    );
  }
  return <>{children}</>;
}
