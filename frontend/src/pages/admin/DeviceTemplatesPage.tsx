import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { CheckCircle2, Cpu, Pencil, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { Breadcrumb } from "@/components/Breadcrumb";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { api, ApiError } from "@/services/api";
import { toast } from "@/stores/toast";
import type { DeviceTemplate } from "@/types";

interface TemplateForm {
  name: string;
  vendor: string;
  model: string;
  cpu: string;
  memory: string;
  storage: string;
  firmware: string;
  nic: string;
  description: string;
}

const EMPTY: TemplateForm = {
  name: "",
  vendor: "",
  model: "",
  cpu: "",
  memory: "",
  storage: "",
  firmware: "",
  nic: "",
  description: "",
};

export function DeviceTemplatesPage() {
  const queryClient = useQueryClient();
  const { data: templates, isLoading } = useQuery({
    queryKey: ["device-templates"],
    queryFn: api.deviceTemplates,
  });
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<DeviceTemplate | null>(null);
  const [deleting, setDeleting] = useState<DeviceTemplate | null>(null);
  const [compliance, setCompliance] = useState<DeviceTemplate | null>(null);
  const [form, setForm] = useState<TemplateForm>(EMPTY);

  const complianceQuery = useQuery({
    queryKey: ["device-templates", compliance?.id, "compliance"],
    queryFn: () => api.templateCompliance(compliance!.id),
    enabled: compliance !== null,
  });

  const invalidate = () =>
    void queryClient.invalidateQueries({ queryKey: ["device-templates"] });

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY);
    setDialogOpen(true);
  };
  const openEdit = (t: DeviceTemplate) => {
    setEditing(t);
    setForm({
      name: t.name,
      vendor: t.vendor ?? "",
      model: t.model ?? "",
      cpu: t.cpu ?? "",
      memory: t.memory ?? "",
      storage: t.storage ?? "",
      firmware: t.firmware ?? "",
      nic: t.nic ?? "",
      description: t.description ?? "",
    });
    setDialogOpen(true);
  };

  const save = useMutation({
    mutationFn: () => {
      const payload = Object.fromEntries(
        Object.entries(form).map(([k, v]) => [k, v || null]),
      );
      payload.name = form.name;
      return editing
        ? api.updateDeviceTemplate(editing.id, payload)
        : api.createDeviceTemplate(payload);
    },
    onSuccess: () => {
      toast.success(editing ? "Template updated" : "Template created", form.name);
      setDialogOpen(false);
      invalidate();
    },
    onError: (err) =>
      toast.error("Save failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteDeviceTemplate(id),
    onSuccess: () => {
      toast.success("Template deleted", deleting?.name);
      setDeleting(null);
      invalidate();
    },
    onError: (err) =>
      toast.error("Delete failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const columns = useMemo<ColumnDef<DeviceTemplate, unknown>[]>(
    () => [
      { accessorKey: "name", header: "Template Name" },
      { accessorKey: "vendor", header: "Vendor", cell: (c) => c.getValue() ?? "-" },
      { accessorKey: "model", header: "Model", cell: (c) => c.getValue() ?? "-" },
      { accessorKey: "cpu", header: "CPU", cell: (c) => c.getValue() ?? "-" },
      { accessorKey: "memory", header: "Memory", cell: (c) => c.getValue() ?? "-" },
      {
        accessorKey: "instance_count",
        header: "Installed",
        cell: ({ row }) => (
          <Badge variant={row.original.instance_count > 0 ? "default" : "muted"}>
            {row.original.instance_count}
          </Badge>
        ),
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button
              variant="ghost"
              size="icon"
              title="Firmware compliance"
              disabled={row.original.instance_count === 0}
              onClick={() => setCompliance(row.original)}
            >
              <ShieldCheck className="h-4 w-4 text-blue-500" />
            </Button>
            <Button variant="ghost" size="icon" onClick={() => openEdit(row.original)}>
              <Pencil className="h-4 w-4 text-gray-500" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              disabled={row.original.instance_count > 0}
              title={
                row.original.instance_count > 0
                  ? "In use by installed devices"
                  : "Delete template"
              }
              onClick={() => setDeleting(row.original)}
            >
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
      <Breadcrumb crumbs={[{ label: "Administration" }, { label: "Device Templates" }]} />
      <p className="text-sm text-gray-500">
        Hardware models reused across installed servers. A template holds only
        hardware specs — never hostnames, IPs or credentials.
      </p>

      <DataTable
        data={templates ?? []}
        columns={columns}
        isLoading={isLoading}
        searchPlaceholder="Search templates…"
        toolbar={
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" /> Create Template
          </Button>
        }
        emptyState={
          <EmptyState
            Icon={Cpu}
            title="No device templates"
            description="Create a hardware template (e.g. HPE DL320 Gen12), then install multiple servers from it."
            action={
              <Button onClick={openCreate}>
                <Plus className="h-4 w-4" /> Create Template
              </Button>
            }
          />
        }
      />

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title={editing ? `Edit Template — ${editing.name}` : "Create Device Template"}
        className="max-w-2xl"
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
        <div className="grid grid-cols-2 gap-3">
          <Field label="Template Name *">
            <Input
              value={form.name}
              autoFocus
              placeholder="e.g. HPE DL320 Gen12"
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Vendor">
            <Input
              value={form.vendor}
              onChange={(e) => setForm({ ...form, vendor: e.target.value })}
            />
          </Field>
          <Field label="Model">
            <Input
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
            />
          </Field>
          <Field label="CPU">
            <Input
              value={form.cpu}
              onChange={(e) => setForm({ ...form, cpu: e.target.value })}
            />
          </Field>
          <Field label="Memory">
            <Input
              value={form.memory}
              onChange={(e) => setForm({ ...form, memory: e.target.value })}
            />
          </Field>
          <Field label="Storage">
            <Input
              value={form.storage}
              onChange={(e) => setForm({ ...form, storage: e.target.value })}
            />
          </Field>
          <Field label="Firmware">
            <Input
              value={form.firmware}
              onChange={(e) => setForm({ ...form, firmware: e.target.value })}
            />
          </Field>
          <Field label="NIC">
            <Input
              value={form.nic}
              onChange={(e) => setForm({ ...form, nic: e.target.value })}
            />
          </Field>
          <div className="col-span-2">
            <Field label="Description">
              <Input
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </Field>
          </div>
        </div>
      </Dialog>

      <Dialog
        open={compliance !== null}
        onClose={() => setCompliance(null)}
        title={`Firmware Compliance — ${compliance?.name ?? ""}`}
        description="Firmware versions across every device using this template. The most common version per component is treated as the baseline."
        className="max-w-3xl"
        footer={
          <Button variant="outline" onClick={() => setCompliance(null)}>
            Close
          </Button>
        }
      >
        {complianceQuery.isLoading || !complianceQuery.data ? (
          <Skeleton className="h-40 w-full" />
        ) : complianceQuery.data.components.length === 0 ? (
          <p className="text-sm text-gray-500">
            No firmware collected yet for this template's devices.
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2 text-sm">
              {complianceQuery.data.compliant ? (
                <Badge variant="success">
                  <CheckCircle2 className="h-3 w-3" /> All compliant
                </Badge>
              ) : (
                <Badge variant="warning">Mismatches found</Badge>
              )}
              <span className="text-gray-500">
                {complianceQuery.data.device_count} device(s)
              </span>
            </div>
            {complianceQuery.data.components.map((component) => (
              <div key={component.component} className="rounded-md border border-gray-200 p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-medium">{component.component}</span>
                  <span className="text-xs text-gray-500">
                    baseline: {component.expected_version ?? "-"}
                  </span>
                </div>
                <Table>
                  <THead>
                    <TR>
                      <TH>Device</TH>
                      <TH>Version</TH>
                      <TH>Status</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {component.devices.map((d) => (
                      <TR key={d.device_id}>
                        <TD>{d.hostname}</TD>
                        <TD className="font-mono text-xs">{d.version ?? "missing"}</TD>
                        <TD>
                          <Badge variant={d.compliant ? "success" : "warning"}>
                            {d.compliant ? "OK" : "Mismatch"}
                          </Badge>
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </div>
            ))}
          </div>
        )}
      </Dialog>

      <ConfirmDialog
        open={deleting !== null}
        title="Delete Template"
        description={`Delete template "${deleting?.name}"? This cannot be undone.`}
        pending={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
