import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Boxes, Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Breadcrumb } from "@/components/Breadcrumb";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { useClusters } from "@/hooks/queries";
import { api, ApiError } from "@/services/api";
import { toast } from "@/stores/toast";
import type { ClusterSummary } from "@/types";

interface ClusterForm {
  name: string;
  vendor: string;
  site: string;
  description: string;
}

const EMPTY_FORM: ClusterForm = { name: "", vendor: "", site: "", description: "" };

export function ClusterManagementPage() {
  const { data: clusters, isLoading } = useClusters();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ClusterSummary | null>(null);
  const [deleting, setDeleting] = useState<ClusterSummary | null>(null);
  const [form, setForm] = useState<ClusterForm>(EMPTY_FORM);

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["clusters"] });

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  };

  const openEdit = (cluster: ClusterSummary) => {
    setEditing(cluster);
    setForm({
      name: cluster.name,
      vendor: cluster.vendor ?? "",
      site: cluster.site ?? "",
      description: cluster.description ?? "",
    });
    setDialogOpen(true);
  };

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        name: form.name,
        vendor: form.vendor || null,
        site: form.site || null,
        description: form.description || null,
      };
      return editing ? api.updateCluster(editing.id, payload) : api.createCluster(payload);
    },
    onSuccess: () => {
      toast.success(editing ? "Cluster updated" : "Cluster created", form.name);
      setDialogOpen(false);
      invalidate();
    },
    onError: (err) =>
      toast.error(
        "Save failed",
        err instanceof ApiError ? err.message : "Unexpected error",
      ),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteCluster(id),
    onSuccess: () => {
      toast.success("Cluster deleted", deleting?.name);
      setDeleting(null);
      invalidate();
    },
    onError: (err) =>
      toast.error(
        "Delete failed",
        err instanceof ApiError ? err.message : "Unexpected error",
      ),
  });

  const columns = useMemo<ColumnDef<ClusterSummary, unknown>[]>(
    () => [
      { accessorKey: "name", header: "Cluster Name" },
      { accessorKey: "site", header: "Site", cell: (c) => c.getValue() ?? "-" },
      {
        accessorKey: "description",
        header: "Description",
        cell: (c) => c.getValue() ?? "-",
      },
      { accessorKey: "rack_count", header: "Racks" },
      { accessorKey: "device_count", header: "Devices" },
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
        crumbs={[{ label: "Administration" }, { label: "Cluster Management" }]}
      />

      <DataTable
        data={clusters ?? []}
        columns={columns}
        isLoading={isLoading}
        searchPlaceholder="Search clusters…"
        toolbar={
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" /> Create Cluster
          </Button>
        }
        emptyState={
          <EmptyState
            Icon={Boxes}
            title="No clusters yet"
            description="Create your first cluster to start organizing racks and devices."
            action={
              <Button onClick={openCreate}>
                <Plus className="h-4 w-4" /> Create Cluster
              </Button>
            }
          />
        }
      />

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title={editing ? `Edit Cluster — ${editing.name}` : "Create Cluster"}
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
          <Field label="Cluster Name *">
            <Input
              value={form.name}
              autoFocus
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Site">
            <Input
              value={form.site}
              placeholder="e.g. Seoul DC1 Room 3"
              onChange={(e) => setForm({ ...form, site: e.target.value })}
            />
          </Field>
          <Field label="Vendor">
            <Input
              value={form.vendor}
              placeholder="e.g. HPE"
              onChange={(e) => setForm({ ...form, vendor: e.target.value })}
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
        title="Delete Cluster"
        description={`Delete cluster "${deleting?.name}"? All racks and devices inside it will be removed. This cannot be undone.`}
        pending={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
