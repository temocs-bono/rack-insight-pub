import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Lock, Pencil, ShieldCheck, Trash2, Users, UsersRound } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Breadcrumb } from "@/components/Breadcrumb";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { PermissionGate } from "@/components/PermissionGate";
import { RoleEditorDialog } from "@/components/RoleEditorDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { usePermissions, useRole } from "@/hooks/queries";
import { api, ApiError } from "@/services/api";
import { toast } from "@/stores/toast";
import type { Permission } from "@/types";

export function RoleDetailsPage() {
  const { roleId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: role, isLoading } = useRole(roleId);
  const { data: permissions } = usePermissions();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const permByCode = useMemo(
    () => new Map((permissions ?? []).map((p) => [p.code, p])),
    [permissions],
  );

  const grouped = useMemo(() => {
    const map = new Map<string, Permission[]>();
    for (const code of role?.permission_codes ?? []) {
      const perm = permByCode.get(code) ?? {
        id: code,
        code,
        name: code,
        category: "Other",
        description: null,
      };
      const list = map.get(perm.category) ?? [];
      list.push(perm);
      map.set(perm.category, list);
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [role?.permission_codes, permByCode]);

  const remove = useMutation({
    mutationFn: () => api.deleteRole(roleId),
    onSuccess: () => {
      toast.success("Role deleted", role?.name);
      void queryClient.invalidateQueries({ queryKey: ["roles"] });
      navigate("/admin/roles");
    },
    onError: (err) =>
      toast.error("Delete failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-6 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (!role) {
    return (
      <EmptyState
        Icon={ShieldCheck}
        title="Role not found"
        description="This role may have been deleted."
        action={
          <Button variant="outline" onClick={() => navigate("/admin/roles")}>
            <ArrowLeft className="h-4 w-4" /> Back to Roles
          </Button>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Breadcrumb
        crumbs={[
          { label: "Access Management" },
          { label: "Roles", to: "/admin/roles" },
          { label: role.name },
        ]}
      />

      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-gray-900">
            {role.name}
            {role.is_system && (
              <Badge variant="muted">
                <Lock className="h-3 w-3" /> System Role
              </Badge>
            )}
          </h1>
          {role.description && (
            <p className="mt-1 text-sm text-gray-500">{role.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => navigate("/admin/roles")}>
            <ArrowLeft className="h-4 w-4" /> Back
          </Button>
          {!role.is_system && (
            <>
              <PermissionGate permission="role.update">
                <Button onClick={() => setEditing(true)}>
                  <Pencil className="h-4 w-4" /> Edit
                </Button>
              </PermissionGate>
              <PermissionGate permission="role.delete">
                <Button variant="destructive" onClick={() => setDeleting(true)}>
                  <Trash2 className="h-4 w-4" /> Delete
                </Button>
              </PermissionGate>
            </>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <Users className="h-8 w-8 text-blue-500" />
            <div>
              <p className="text-2xl font-semibold">{role.effective_user_count}</p>
              <p className="text-xs uppercase tracking-wide text-gray-400">Effective Users</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <UsersRound className="h-8 w-8 text-blue-500" />
            <div>
              <p className="text-2xl font-semibold">{role.user_groups.length}</p>
              <p className="text-xs uppercase tracking-wide text-gray-400">User Groups</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <ShieldCheck className="h-8 w-8 text-blue-500" />
            <div>
              <p className="text-2xl font-semibold">{role.permission_codes.length}</p>
              <p className="text-xs uppercase tracking-wide text-gray-400">Permissions</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="p-4">
            <h3 className="mb-3 text-sm font-semibold text-gray-900">Assigned Permissions</h3>
            {grouped.length === 0 ? (
              <p className="text-sm text-gray-400">No permissions assigned.</p>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {grouped.map(([category, perms]) => (
                  <div key={category} className="flex flex-col gap-1">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                      {category}
                    </p>
                    {perms.map((perm) => (
                      <div key={perm.code} className="flex items-center gap-2 text-sm">
                        <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-700">
                          {perm.code}
                        </code>
                        <span className="text-gray-600">{perm.name}</span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <h3 className="mb-3 text-sm font-semibold text-gray-900">Assigned User Groups</h3>
            {role.user_groups.length === 0 ? (
              <p className="text-sm text-gray-400">
                Not bound to any group yet. Assign this role from a User Group editor.
              </p>
            ) : (
              <div className="flex flex-col gap-1">
                {role.user_groups.map((g) => (
                  <div key={g.id} className="flex items-center gap-2 text-sm text-gray-700">
                    <UsersRound className="h-4 w-4 text-gray-400" />
                    {g.name}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <RoleEditorDialog open={editing} role={role} onClose={() => setEditing(false)} />

      <ConfirmDialog
        open={deleting}
        title="Delete Role"
        description={`Delete role "${role.name}"? Any group bindings using it will be removed.`}
        pending={remove.isPending}
        onConfirm={() => remove.mutate()}
        onClose={() => setDeleting(false)}
      />
    </div>
  );
}
