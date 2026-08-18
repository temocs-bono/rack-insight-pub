import type { ColumnDef } from "@tanstack/react-table";
import { ChevronRight, Lock, Plus, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Breadcrumb } from "@/components/Breadcrumb";
import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { PermissionGate } from "@/components/PermissionGate";
import { RoleEditorDialog } from "@/components/RoleEditorDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useRoles } from "@/hooks/queries";
import type { Role } from "@/types";

export function RolesPage() {
  const { data: roles, isLoading } = useRoles();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);

  const columns = useMemo<ColumnDef<Role, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Role",
        cell: ({ row }) => (
          <button
            type="button"
            onClick={() => navigate(`/admin/roles/${row.original.id}`)}
            className="flex items-center gap-2 font-medium text-blue-700 hover:underline"
          >
            {row.original.name}
            {row.original.is_system && (
              <Badge variant="muted">
                <Lock className="h-3 w-3" /> System
              </Badge>
            )}
          </button>
        ),
      },
      {
        accessorKey: "description",
        header: "Description",
        cell: (c) => (c.getValue() as string) || "-",
      },
      {
        id: "permissions",
        header: "Permissions",
        cell: ({ row }) => (
          <Badge variant="default">{row.original.permission_codes.length}</Badge>
        ),
      },
      {
        id: "open",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex justify-end">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate(`/admin/roles/${row.original.id}`)}
              title="Open role details"
            >
              <ChevronRight className="h-4 w-4 text-gray-400" />
            </Button>
          </div>
        ),
      },
    ],
    [navigate],
  );

  return (
    <div className="flex flex-col gap-4">
      <Breadcrumb crumbs={[{ label: "Access Management" }, { label: "Roles" }]} />

      <DataTable
        data={roles ?? []}
        columns={columns}
        isLoading={isLoading}
        searchPlaceholder="Search roles…"
        toolbar={
          <PermissionGate permission="role.create">
            <Button onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" /> Create Role
            </Button>
          </PermissionGate>
        }
        emptyState={
          <EmptyState
            Icon={ShieldCheck}
            title="No roles"
            description="Roles bundle permissions. Assign them to user groups to grant access."
          />
        }
      />

      <RoleEditorDialog
        open={creating}
        role={null}
        onClose={() => setCreating(false)}
        onSaved={(id) => navigate(`/admin/roles/${id}`)}
      />
    </div>
  );
}
