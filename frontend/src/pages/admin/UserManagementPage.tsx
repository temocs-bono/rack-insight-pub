import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Pencil, Plus, Trash2, Users } from "lucide-react";
import { useMemo, useState } from "react";
import { Breadcrumb } from "@/components/Breadcrumb";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { PermissionGate } from "@/components/PermissionGate";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useUserGroups, useUsers } from "@/hooks/queries";
import { api, ApiError } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import { toast } from "@/stores/toast";
import type { User, UserRole, UserStatus } from "@/types";

const MIN_PASSWORD_LENGTH = 8;

interface UserForm {
  username: string;
  password: string;
  role: UserRole;
  display_name: string;
  email: string;
  status: UserStatus;
  group_ids: string[];
}

const EMPTY_FORM: UserForm = {
  username: "",
  password: "",
  role: "USER",
  display_name: "",
  email: "",
  status: "ACTIVE",
  group_ids: [],
};

export function UserManagementPage() {
  const { data: users, isLoading } = useUsers();
  const { data: groups } = useUserGroups();
  const { user: currentUser } = useAuthStore();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [deleting, setDeleting] = useState<User | null>(null);
  const [form, setForm] = useState<UserForm>(EMPTY_FORM);

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["users"] });

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  };

  const openEdit = (user: User) => {
    setEditing(user);
    setForm({
      username: user.username,
      password: "",
      role: user.role,
      display_name: user.display_name ?? "",
      email: user.email ?? "",
      status: user.status,
      group_ids: user.group_ids ?? [],
    });
    setDialogOpen(true);
  };

  const toggleGroup = (id: string) =>
    setForm((f) => ({
      ...f,
      group_ids: f.group_ids.includes(id)
        ? f.group_ids.filter((g) => g !== id)
        : [...f.group_ids, id],
    }));

  const save = useMutation({
    mutationFn: () => {
      const base = {
        role: form.role,
        display_name: form.display_name || null,
        email: form.email || null,
        status: form.status,
        group_ids: form.group_ids,
      };
      if (editing) {
        const payload: Record<string, unknown> = { ...base };
        if (form.password) payload.password = form.password;
        return api.updateUser(editing.id, payload);
      }
      return api.createUser({
        ...base,
        username: form.username,
        password: form.password,
      });
    },
    onSuccess: () => {
      toast.success(editing ? "User updated" : "User created", form.username);
      setDialogOpen(false);
      invalidate();
    },
    onError: (err) =>
      toast.error("Save failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteUser(id),
    onSuccess: () => {
      toast.success("User deleted", deleting?.username);
      setDeleting(null);
      invalidate();
    },
    onError: (err) =>
      toast.error("Delete failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const passwordInvalid =
    (!editing && form.password.length < MIN_PASSWORD_LENGTH) ||
    (Boolean(form.password) && form.password.length < MIN_PASSWORD_LENGTH);

  const groupNameById = useMemo(
    () => new Map((groups ?? []).map((g) => [g.id, g.name])),
    [groups],
  );

  const columns = useMemo<ColumnDef<User, unknown>[]>(
    () => [
      { accessorKey: "username", header: "Username" },
      {
        accessorKey: "display_name",
        header: "Display Name",
        cell: (c) => (c.getValue() as string) || "-",
      },
      {
        accessorKey: "email",
        header: "Email",
        cell: (c) => (c.getValue() as string) || "-",
      },
      {
        accessorKey: "role",
        header: "Role",
        cell: ({ row }) => (
          <Badge variant={row.original.role === "ADMIN" ? "default" : "muted"}>
            {row.original.role}
          </Badge>
        ),
      },
      {
        id: "groups",
        header: "Groups",
        cell: ({ row }) => {
          const names = (row.original.group_ids ?? [])
            .map((id) => groupNameById.get(id))
            .filter(Boolean);
          return names.length ? names.join(", ") : "-";
        },
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => (
          <Badge variant={row.original.enabled ? "success" : "critical"}>
            {row.original.enabled ? "Active" : "Disabled"}
          </Badge>
        ),
      },
      {
        accessorKey: "last_login",
        header: "Last Login",
        cell: (c) => (c.getValue() ? new Date(String(c.getValue())).toLocaleString() : "-"),
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <PermissionGate permission="user.update">
              <Button variant="ghost" size="icon" onClick={() => openEdit(row.original)}>
                <Pencil className="h-4 w-4 text-gray-500" />
              </Button>
            </PermissionGate>
            <PermissionGate permission="user.delete">
              <Button
                variant="ghost"
                size="icon"
                disabled={row.original.id === currentUser?.id}
                onClick={() => setDeleting(row.original)}
              >
                <Trash2 className="h-4 w-4 text-red-500" />
              </Button>
            </PermissionGate>
          </div>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [currentUser?.id, groupNameById],
  );

  return (
    <div className="flex flex-col gap-4">
      <Breadcrumb crumbs={[{ label: "Access Management" }, { label: "Users" }]} />

      <DataTable
        data={users ?? []}
        columns={columns}
        isLoading={isLoading}
        searchPlaceholder="Search users…"
        toolbar={
          <PermissionGate permission="user.create">
            <Button onClick={openCreate}>
              <Plus className="h-4 w-4" /> Create User
            </Button>
          </PermissionGate>
        }
        emptyState={
          <EmptyState
            Icon={Users}
            title="No users"
            description="Create accounts and assign them to user groups to grant access."
            action={
              <PermissionGate permission="user.create">
                <Button onClick={openCreate}>
                  <Plus className="h-4 w-4" /> Create User
                </Button>
              </PermissionGate>
            }
          />
        }
      />

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title={editing ? `Edit User — ${editing.username}` : "Create User"}
        footer={
          <>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => save.mutate()}
              disabled={save.isPending || (!editing && !form.username) || passwordInvalid}
            >
              {save.isPending ? "Saving…" : editing ? "Save Changes" : "Create"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <Field label="Username *">
            <Input
              value={form.username}
              disabled={Boolean(editing)}
              autoFocus={!editing}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
            />
          </Field>
          <Field label="Display Name">
            <Input
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            />
          </Field>
          <Field label="Email">
            <Input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </Field>
          <Field
            label={
              editing
                ? "New Password (leave blank to keep current)"
                : `Password * (min ${MIN_PASSWORD_LENGTH} chars)`
            }
          >
            <Input
              type="password"
              value={form.password}
              autoComplete="new-password"
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </Field>
          <Field label="Role">
            <Select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}
            >
              <option value="USER">USER</option>
              <option value="ADMIN">ADMIN</option>
            </Select>
          </Field>
          <Field label="Status">
            <Select
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value as UserStatus })}
            >
              <option value="ACTIVE">Active</option>
              <option value="DISABLED">Disabled</option>
            </Select>
          </Field>
          {groups && groups.length > 0 && (
            <Field label="User Groups">
              <div className="flex flex-col gap-1 rounded-md border border-gray-200 p-2">
                {groups.map((g) => (
                  <label key={g.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={form.group_ids.includes(g.id)}
                      onChange={() => toggleGroup(g.id)}
                    />
                    {g.name}
                  </label>
                ))}
              </div>
            </Field>
          )}
        </div>
      </Dialog>

      <ConfirmDialog
        open={deleting !== null}
        title="Delete User"
        description={`Delete user "${deleting?.username}"? This cannot be undone.`}
        pending={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
