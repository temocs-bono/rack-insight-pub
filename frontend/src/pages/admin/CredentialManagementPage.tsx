import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { KeyRound, Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Breadcrumb } from "@/components/Breadcrumb";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useCredentials } from "@/hooks/queries";
import { api, ApiError } from "@/services/api";
import { toast } from "@/stores/toast";
import type { Credential, CredentialType } from "@/types";

const CREDENTIAL_TYPES: CredentialType[] = ["REDFISH", "SSH", "SNMP"];

interface CredentialForm {
  name: string;
  credential_type: CredentialType;
  username: string;
  password: string;
  description: string;
}

const EMPTY_FORM: CredentialForm = {
  name: "",
  credential_type: "REDFISH",
  username: "",
  password: "",
  description: "",
};

export function CredentialManagementPage() {
  const { data: credentials, isLoading } = useCredentials();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Credential | null>(null);
  const [deleting, setDeleting] = useState<Credential | null>(null);
  const [form, setForm] = useState<CredentialForm>(EMPTY_FORM);

  const invalidate = () =>
    void queryClient.invalidateQueries({ queryKey: ["credentials"] });

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  };

  const openEdit = (credential: Credential) => {
    setEditing(credential);
    setForm({
      name: credential.name,
      credential_type: credential.credential_type,
      username: credential.username ?? "",
      password: "",
      description: credential.description ?? "",
    });
    setDialogOpen(true);
  };

  const save = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = {
        name: form.name,
        credential_type: form.credential_type,
        username: form.username || null,
        description: form.description || null,
      };
      // Password is write-only; empty input on edit keeps the stored password.
      if (form.password) payload.password = form.password;
      return editing
        ? api.updateCredential(editing.id, payload)
        : api.createCredential(payload);
    },
    onSuccess: () => {
      toast.success(editing ? "Credential updated" : "Credential created", form.name);
      setDialogOpen(false);
      invalidate();
    },
    onError: (err) =>
      toast.error("Save failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteCredential(id),
    onSuccess: () => {
      toast.success("Credential deleted", deleting?.name);
      setDeleting(null);
      invalidate();
    },
    onError: (err) =>
      toast.error("Delete failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const columns = useMemo<ColumnDef<Credential, unknown>[]>(
    () => [
      { accessorKey: "name", header: "Name" },
      {
        accessorKey: "credential_type",
        header: "Type",
        cell: ({ row }) => <Badge variant="muted">{row.original.credential_type}</Badge>,
      },
      { accessorKey: "username", header: "Username", cell: (c) => c.getValue() ?? "-" },
      {
        id: "password",
        header: "Password",
        enableSorting: false,
        cell: ({ row }) =>
          row.original.has_password ? (
            <span className="font-mono text-gray-400">••••••••</span>
          ) : (
            <span className="text-gray-400">not set</span>
          ),
      },
      {
        accessorKey: "description",
        header: "Description",
        cell: (c) => c.getValue() ?? "-",
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button variant="ghost" size="icon" onClick={() => openEdit(row.original)}>
              <Pencil className="h-4 w-4 text-gray-500" />
            </Button>
            <Button variant="ghost" size="icon" onClick={() => setDeleting(row.original)}>
              <Trash2 className="h-4 w-4 text-red-500" />
            </Button>
          </div>
        ),
      },
    ],
    [],
  );

  return (
    <div className="flex flex-col gap-4">
      <Breadcrumb
        crumbs={[{ label: "Administration" }, { label: "Credential Management" }]}
      />

      <DataTable
        data={credentials ?? []}
        columns={columns}
        isLoading={isLoading}
        searchPlaceholder="Search credentials…"
        toolbar={
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" /> Create Credential
          </Button>
        }
        emptyState={
          <EmptyState
            Icon={KeyRound}
            title="No credentials yet"
            description="Store Redfish, SSH or SNMP credentials once and reuse them across devices."
            action={
              <Button onClick={openCreate}>
                <Plus className="h-4 w-4" /> Create Credential
              </Button>
            }
          />
        }
      />

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title={editing ? `Edit Credential — ${editing.name}` : "Create Credential"}
        footer={
          <>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => save.mutate()} disabled={!form.name || save.isPending}>
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
              placeholder="e.g. HPE iLO default"
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Type *">
            <Select
              value={form.credential_type}
              onChange={(e) =>
                setForm({ ...form, credential_type: e.target.value as CredentialType })
              }
            >
              {CREDENTIAL_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={form.credential_type === "SNMP" ? "Community Owner" : "Username"}>
            <Input
              value={form.username}
              autoComplete="off"
              onChange={(e) => setForm({ ...form, username: e.target.value })}
            />
          </Field>
          <Field
            label={form.credential_type === "SNMP" ? "Community String" : "Password"}
          >
            <Input
              type="password"
              value={form.password}
              autoComplete="new-password"
              placeholder={editing?.has_password ? "(unchanged)" : ""}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </Field>
          <Field label="Description">
            <Input
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </Field>
        </div>
      </Dialog>

      <ConfirmDialog
        open={deleting !== null}
        title="Delete Credential"
        description={`Delete credential "${deleting?.name}"? Devices referencing it will fall back to their inline credentials.`}
        pending={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
