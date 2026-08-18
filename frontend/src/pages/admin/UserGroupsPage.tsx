import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Lock, Pencil, Plus, Trash2, UsersRound } from "lucide-react";
import { useMemo, useState } from "react";
import { Breadcrumb } from "@/components/Breadcrumb";
import { CheckboxList } from "@/components/CheckboxList";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { PermissionGate } from "@/components/PermissionGate";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { useRoles, useUserGroups, useUsers } from "@/hooks/queries";
import { api, ApiError } from "@/services/api";
import { toast } from "@/stores/toast";
import type { UserGroup } from "@/types";

interface GroupForm {
  name: string;
  description: string;
  member_ids: string[];
  role_ids: string[];
}

const EMPTY_FORM: GroupForm = { name: "", description: "", member_ids: [], role_ids: [] };

export function UserGroupsPage() {
  const { data: groups, isLoading } = useUserGroups();
  const { data: users } = useUsers();
  const { data: roles } = useRoles();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<UserGroup | null>(null);
  const [deleting, setDeleting] = useState<UserGroup | null>(null);
  const [form, setForm] = useState<GroupForm>(EMPTY_FORM);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["user-groups"] });
    void queryClient.invalidateQueries({ queryKey: ["users"] });
    void queryClient.invalidateQueries({ queryKey: ["roles"] });
    void queryClient.invalidateQueries({ queryKey: ["role"] });
  };

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  };

  const openEdit = (group: UserGroup) => {
    setEditing(group);
    setForm({
      name: group.name,
      description: group.description ?? "",
      member_ids: group.member_ids,
      role_ids: group.role_ids,
    });
    setDialogOpen(true);
  };

  const toggle = (key: "member_ids" | "role_ids", id: string) =>
    setForm((f) => ({
      ...f,
      [key]: f[key].includes(id) ? f[key].filter((x) => x !== id) : [...f[key], id],
    }));

  const save = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = {
        description: form.description || null,
        member_ids: form.member_ids,
        role_ids: form.role_ids,
      };
      // A system group's name cannot change; only send name for custom groups.
      if (!editing?.is_system) payload.name = form.name;
      return editing
        ? api.updateUserGroup(editing.id, payload)
        : api.createUserGroup(payload);
    },
    onSuccess: () => {
      toast.success(editing ? "Group updated" : "Group created", form.name);
      setDialogOpen(false);
      invalidate();
    },
    onError: (err) =>
      toast.error("Save failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteUserGroup(id),
    onSuccess: () => {
      toast.success("Group deleted", deleting?.name);
      setDeleting(null);
      invalidate();
    },
    onError: (err) =>
      toast.error("Delete failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const columns = useMemo<ColumnDef<UserGroup, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Group",
        cell: ({ row }) => (
          <span className="flex items-center gap-2 font-medium">
            {row.original.name}
            {row.original.is_system && (
              <Badge variant="muted">
                <Lock className="h-3 w-3" /> System
              </Badge>
            )}
          </span>
        ),
      },
      {
        accessorKey: "description",
        header: "Description",
        cell: (c) => (c.getValue() as string) || "-",
      },
      {
        id: "roles",
        header: "Roles",
        cell: ({ row }) =>
          row.original.role_names.length
            ? row.original.role_names.map((r) => (
                <Badge key={r} variant="default" className="mr-1">
                  {r}
                </Badge>
              ))
            : "-",
      },
      {
        accessorKey: "member_count",
        header: "Members",
        cell: ({ row }) => <Badge variant="muted">{row.original.member_count}</Badge>,
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <PermissionGate permission="group.update">
              <Button variant="ghost" size="icon" onClick={() => openEdit(row.original)}>
                <Pencil className="h-4 w-4 text-gray-500" />
              </Button>
            </PermissionGate>
            <PermissionGate permission="group.delete">
              <Button
                variant="ghost"
                size="icon"
                disabled={row.original.is_system}
                onClick={() => setDeleting(row.original)}
              >
                <Trash2 className="h-4 w-4 text-red-500" />
              </Button>
            </PermissionGate>
          </div>
        ),
      },
    ],
    [],
  );

  const memberOptions = useMemo(
    () =>
      (users ?? []).map((u) => ({
        value: u.id,
        label: u.display_name ? `${u.display_name} (${u.username})` : u.username,
      })),
    [users],
  );

  const roleOptions = useMemo(
    () => (roles ?? []).map((r) => ({ value: r.id, label: r.name, hint: r.description ?? undefined })),
    [roles],
  );

  return (
    <div className="flex flex-col gap-4">
      <Breadcrumb crumbs={[{ label: "Access Management" }, { label: "User Groups" }]} />

      <DataTable
        data={groups ?? []}
        columns={columns}
        isLoading={isLoading}
        searchPlaceholder="Search groups…"
        toolbar={
          <PermissionGate permission="group.create">
            <Button onClick={openCreate}>
              <Plus className="h-4 w-4" /> Create Group
            </Button>
          </PermissionGate>
        }
        emptyState={
          <EmptyState
            Icon={UsersRound}
            title="No user groups"
            description="Groups collect users and grant them roles. Create one to get started."
          />
        }
      />

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title={editing ? `Edit Group — ${editing.name}` : "Create User Group"}
        className="max-w-2xl"
        footer={
          <>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => save.mutate()} disabled={save.isPending || !form.name}>
              {save.isPending ? "Saving…" : editing ? "Save Changes" : "Create"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <Field label="Name *">
            <Input
              value={form.name}
              autoFocus
              disabled={editing?.is_system}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Description">
            <Input
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </Field>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label={`Roles (${form.role_ids.length} selected)`}>
              <CheckboxList
                options={roleOptions}
                selected={form.role_ids}
                onToggle={(id) => toggle("role_ids", id)}
                emptyText="No roles defined."
              />
            </Field>
            <Field label={`Members (${form.member_ids.length} selected)`}>
              <CheckboxList
                options={memberOptions}
                selected={form.member_ids}
                onToggle={(id) => toggle("member_ids", id)}
                emptyText="No users available."
              />
            </Field>
          </div>
        </div>
      </Dialog>

      <ConfirmDialog
        open={deleting !== null}
        title="Delete User Group"
        description={`Delete group "${deleting?.name}"? Members are not deleted, but they lose the roles granted through this group.`}
        pending={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
