import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { HardDrive, Layers, LogOut, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Breadcrumb } from "@/components/Breadcrumb";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { ProvisioningWizard } from "@/features/provisioning/ProvisioningWizard";
import {
  useClusterRacks,
  useClusters,
  useCredentials,
  useDeviceTemplates,
  useDevices,
  useRackLayout,
} from "@/hooks/queries";
import { api, ApiError } from "@/services/api";
import { toast } from "@/stores/toast";
import type { Device, DeviceOrientation, DeviceType } from "@/types";

const COLLECTOR_TYPES = ["REDFISH", "SSH", "CISCO"] as const;
const DEVICE_TYPES: DeviceType[] = ["SERVER", "SWITCH"];
const HEIGHTS = [1, 2, 4];

interface DeviceForm {
  hostname: string;
  display_name: string;
  device_type: DeviceType;
  template_id: string;
  vendor: string;
  model: string;
  management_ip: string;
  ilo_ip: string;
  orientation: DeviceOrientation;
  collector_types: string[];
  redfish_credential_id: string;
  ssh_credential_id: string;
  snmp_credential_id: string;
  u_position: string;
  height: number;
}

const EMPTY_FORM: DeviceForm = {
  hostname: "",
  display_name: "",
  device_type: "SERVER",
  template_id: "",
  vendor: "",
  model: "",
  management_ip: "",
  ilo_ip: "",
  orientation: "FRONT",
  collector_types: [],
  redfish_credential_id: "",
  ssh_credential_id: "",
  snmp_credential_id: "",
  u_position: "",
  height: 1,
};

export function DeviceManagementPage() {
  const { data: clusters } = useClusters();
  const [clusterId, setClusterId] = useState("");
  const { data: racks } = useClusterRacks(clusterId);
  const [rackId, setRackId] = useState("");
  const { data: devices, isLoading } = useDevices(rackId || undefined);
  const { data: layout } = useRackLayout(rackId);
  const { data: credentials } = useCredentials();
  const { data: templates } = useDeviceTemplates();
  const queryClient = useQueryClient();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Device | null>(null);
  const [deleting, setDeleting] = useState<Device | null>(null);
  const [unassigning, setUnassigning] = useState<Device | null>(null);
  const [form, setForm] = useState<DeviceForm>(EMPTY_FORM);
  const [wizardOpen, setWizardOpen] = useState(false);

  useEffect(() => {
    if (!clusterId && clusters && clusters.length > 0) setClusterId(clusters[0].id);
  }, [clusters, clusterId]);

  useEffect(() => {
    if (racks && racks.length > 0 && !racks.some((r) => r.id === rackId)) {
      setRackId(racks[0].id);
    } else if (racks && racks.length === 0) {
      setRackId("");
    }
  }, [racks, rackId]);

  const uPositionByDevice = useMemo(() => {
    const map = new Map<string, { u: number; h: number }>();
    for (const unit of layout?.units ?? []) {
      if (unit.device) map.set(unit.device.id, { u: unit.u_position, h: unit.height });
    }
    return map;
  }, [layout]);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["devices"] });
    void queryClient.invalidateQueries({ queryKey: ["rack", rackId, "layout"] });
    void queryClient.invalidateQueries({ queryKey: ["clusters"] });
    void queryClient.invalidateQueries({ queryKey: ["cluster", clusterId, "racks"] });
  };

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  };

  const openEdit = (device: Device) => {
    const position = uPositionByDevice.get(device.id);
    setEditing(device);
    setForm({
      hostname: device.hostname,
      display_name: device.display_name ?? "",
      device_type: device.device_type,
      template_id: device.template_id ?? "",
      vendor: device.vendor ?? "",
      model: device.model ?? "",
      management_ip: device.management_ip ?? "",
      ilo_ip: device.ilo_ip ?? "",
      orientation: device.orientation,
      collector_types: device.collector_types
        ? device.collector_types.split(",").filter(Boolean)
        : [],
      redfish_credential_id: device.redfish_credential_id ?? "",
      ssh_credential_id: device.ssh_credential_id ?? "",
      snmp_credential_id: device.snmp_credential_id ?? "",
      u_position: position ? String(position.u) : "",
      height: position?.h ?? 1,
    });
    setDialogOpen(true);
  };

  const save = useMutation({
    mutationFn: async () => {
      const base = {
        hostname: form.hostname,
        display_name: form.display_name || null,
        device_type: form.device_type,
        template_id: form.template_id || null,
        vendor: form.vendor || null,
        model: form.model || null,
        management_ip: form.management_ip || null,
        ilo_ip: form.ilo_ip || null,
        orientation: form.orientation,
        collector_types: form.collector_types,
        redfish_credential_id: form.redfish_credential_id || null,
        ssh_credential_id: form.ssh_credential_id || null,
        snmp_credential_id: form.snmp_credential_id || null,
      };
      if (editing) {
        await api.updateDevice(editing.id, base);
        if (form.u_position) {
          await api.moveDevice(editing.id, {
            u_position: Number(form.u_position),
            height: form.height,
          });
        }
      } else {
        await api.createDevice({
          ...base,
          rack_id: rackId,
          u_position: form.u_position ? Number(form.u_position) : null,
          height: form.height,
        });
      }
    },
    onSuccess: () => {
      toast.success(editing ? "Device updated" : "Device registered", form.hostname);
      setDialogOpen(false);
      invalidate();
    },
    onError: (err) =>
      toast.error("Save failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteDevice(id),
    onSuccess: () => {
      toast.success("Device deleted", deleting?.hostname);
      setDeleting(null);
      invalidate();
    },
    onError: (err) =>
      toast.error("Delete failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const unassign = useMutation({
    mutationFn: (id: string) => api.unassignDevice(id),
    onSuccess: () => {
      toast.success("Removed from rack", unassigning?.hostname);
      setUnassigning(null);
      invalidate();
    },
    onError: (err) =>
      toast.error("Remove failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  // Choosing a template auto-fills vendor/model (kept editable for overrides).
  const applyTemplate = (templateId: string) => {
    const template = templates?.find((t) => t.id === templateId);
    setForm((prev) => ({
      ...prev,
      template_id: templateId,
      vendor: template?.vendor ?? prev.vendor,
      model: template?.model ?? prev.model,
    }));
  };

  const toggleCollectorType = (type: string) => {
    setForm((prev) => ({
      ...prev,
      collector_types: prev.collector_types.includes(type)
        ? prev.collector_types.filter((t) => t !== type)
        : [...prev.collector_types, type],
    }));
  };

  const credentialOptions = (type: string) =>
    credentials?.filter((c) => c.credential_type === type) ?? [];

  const columns = useMemo<ColumnDef<Device, unknown>[]>(
    () => [
      { accessorKey: "hostname", header: "Name" },
      { accessorKey: "device_type", header: "Type" },
      { accessorKey: "vendor", header: "Vendor", cell: (c) => c.getValue() ?? "-" },
      { accessorKey: "model", header: "Model", cell: (c) => c.getValue() ?? "-" },
      {
        accessorKey: "management_ip",
        header: "Management IP",
        cell: (c) => c.getValue() ?? "-",
      },
      {
        id: "u_position",
        header: "U",
        cell: ({ row }) => {
          const pos = uPositionByDevice.get(row.original.id);
          return pos ? `U${pos.u} (${pos.h}U)` : "-";
        },
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => {
          const placed = uPositionByDevice.has(row.original.id);
          return (
            <div className="flex justify-end gap-1">
              <Button variant="ghost" size="icon" onClick={() => openEdit(row.original)}>
                <Pencil className="h-4 w-4 text-gray-500" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                disabled={!placed}
                title={placed ? "Remove from rack slot" : "Not installed in a slot"}
                onClick={() => setUnassigning(row.original)}
              >
                <LogOut className="h-4 w-4 text-orange-500" />
              </Button>
              <Button variant="ghost" size="icon" onClick={() => setDeleting(row.original)}>
                <Trash2 className="h-4 w-4 text-red-500" />
              </Button>
            </div>
          );
        },
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [uPositionByDevice],
  );

  const showRedfish = form.collector_types.includes("REDFISH");
  const showSSH = form.collector_types.includes("SSH") || form.collector_types.includes("CISCO");

  return (
    <div className="flex flex-col gap-4">
      <Breadcrumb crumbs={[{ label: "Administration" }, { label: "Installed Devices" }]} />

      <div className="flex items-end gap-3">
        <Field label="Cluster">
          <Select
            className="w-56"
            value={clusterId}
            onChange={(e) => setClusterId(e.target.value)}
          >
            {clusters?.map((cluster) => (
              <option key={cluster.id} value={cluster.id}>
                {cluster.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Rack">
          <Select className="w-56" value={rackId} onChange={(e) => setRackId(e.target.value)}>
            {racks?.map((rack) => (
              <option key={rack.id} value={rack.id}>
                {rack.name}
              </option>
            ))}
          </Select>
        </Field>
        {rackId && (
          <Link
            to={`/racks/${rackId}`}
            className="pb-2 text-sm text-blue-600 hover:underline"
          >
            Open Rack View →
          </Link>
        )}
      </div>

      <DataTable
        data={devices ?? []}
        columns={columns}
        isLoading={isLoading && Boolean(rackId)}
        searchPlaceholder="Search devices…"
        toolbar={
          <>
            <Button
              variant="outline"
              onClick={() => setWizardOpen(true)}
              disabled={!rackId}
              title="Provision several servers with generated hostnames/IPs, then review"
            >
              <Layers className="h-4 w-4" /> Provision Multiple Devices
            </Button>
            <Button onClick={openCreate} disabled={!rackId}>
              <Plus className="h-4 w-4" /> Register Device
            </Button>
          </>
        }
        emptyState={
          <EmptyState
            Icon={HardDrive}
            title="No devices in this rack"
            description="Register a server or switch to start collecting inventory."
            action={
              <Button onClick={openCreate} disabled={!rackId}>
                <Plus className="h-4 w-4" /> Register Device
              </Button>
            }
          />
        }
      />

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title={editing ? `Edit Device — ${editing.hostname}` : "Register Device"}
        className="max-w-2xl"
        footer={
          <>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => save.mutate()}
              disabled={!form.hostname || save.isPending}
            >
              {save.isPending ? "Saving…" : editing ? "Save Changes" : "Register"}
            </Button>
          </>
        }
      >
        <div className="grid grid-cols-2 gap-3">
          <Field label="Name (Hostname) *">
            <Input
              value={form.hostname}
              autoFocus
              onChange={(e) => setForm({ ...form, hostname: e.target.value })}
            />
          </Field>
          <Field label="Display Name">
            <Input
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            />
          </Field>
          <Field label="Type">
            <Select
              value={form.device_type}
              onChange={(e) =>
                setForm({ ...form, device_type: e.target.value as DeviceType })
              }
            >
              {DEVICE_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Device Template">
            <Select
              value={form.template_id}
              onChange={(e) => applyTemplate(e.target.value)}
            >
              <option value="">(None — enter vendor/model manually)</option>
              {templates?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Vendor">
            <Input
              value={form.vendor}
              placeholder="e.g. HPE / Cisco"
              onChange={(e) => setForm({ ...form, vendor: e.target.value })}
            />
          </Field>
          <Field label="Model">
            <Input
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
            />
          </Field>
          <Field label="Management IP">
            <Input
              value={form.management_ip}
              placeholder="192.168.x.x"
              onChange={(e) => setForm({ ...form, management_ip: e.target.value })}
            />
          </Field>
          <Field label="Start U">
            <Input
              type="number"
              min={1}
              value={form.u_position}
              placeholder="U position"
              onChange={(e) => setForm({ ...form, u_position: e.target.value })}
            />
          </Field>
          <Field label="Height (U)">
            <Select
              value={form.height}
              onChange={(e) => setForm({ ...form, height: Number(e.target.value) })}
            >
              {HEIGHTS.map((h) => (
                <option key={h} value={h}>
                  {h}U
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Orientation">
            <Select
              value={form.orientation}
              onChange={(e) =>
                setForm({ ...form, orientation: e.target.value as DeviceOrientation })
              }
            >
              <option value="FRONT">Front</option>
              <option value="REAR">Rear</option>
            </Select>
          </Field>

          <div className="col-span-2 flex flex-col gap-1">
            <Label>Collector Type</Label>
            <div className="flex gap-4">
              {COLLECTOR_TYPES.map((type) => (
                <label key={type} className="flex items-center gap-1.5 text-sm">
                  <input
                    type="checkbox"
                    checked={form.collector_types.includes(type)}
                    onChange={() => toggleCollectorType(type)}
                  />
                  {type === "REDFISH" ? "Redfish" : type === "SSH" ? "SSH" : "Cisco"}
                </label>
              ))}
            </div>
          </div>

          {showRedfish && (
            <>
              <Field label="iLO / BMC IP">
                <Input
                  value={form.ilo_ip}
                  placeholder="192.168.x.x"
                  onChange={(e) => setForm({ ...form, ilo_ip: e.target.value })}
                />
              </Field>
              <Field label="Redfish Credential">
                <Select
                  value={form.redfish_credential_id}
                  onChange={(e) =>
                    setForm({ ...form, redfish_credential_id: e.target.value })
                  }
                >
                  <option value="">(None)</option>
                  {credentialOptions("REDFISH").map((cred) => (
                    <option key={cred.id} value={cred.id}>
                      {cred.name}
                    </option>
                  ))}
                </Select>
              </Field>
            </>
          )}
          {showSSH && (
            <Field label="SSH Credential">
              <Select
                value={form.ssh_credential_id}
                onChange={(e) => setForm({ ...form, ssh_credential_id: e.target.value })}
              >
                <option value="">(None)</option>
                {credentialOptions("SSH").map((cred) => (
                  <option key={cred.id} value={cred.id}>
                    {cred.name}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <Field label="SNMP Credential">
            <Select
              value={form.snmp_credential_id}
              onChange={(e) => setForm({ ...form, snmp_credential_id: e.target.value })}
            >
              <option value="">(None)</option>
              {credentialOptions("SNMP").map((cred) => (
                <option key={cred.id} value={cred.id}>
                  {cred.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </Dialog>

      <ProvisioningWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        rackId={rackId}
        rackName={racks?.find((r) => r.id === rackId)?.name ?? ""}
        templates={templates ?? []}
        credentials={credentials ?? []}
        onCreated={invalidate}
      />

      <ConfirmDialog
        open={unassigning !== null}
        title="Remove Device from Rack"
        description={`Remove "${unassigning?.hostname}" from its rack slot? The device stays registered and can be reinstalled later.`}
        confirmLabel="Remove"
        pending={unassign.isPending}
        onConfirm={() => unassigning && unassign.mutate(unassigning.id)}
        onClose={() => setUnassigning(null)}
      />

      <ConfirmDialog
        open={deleting !== null}
        title="Delete Device"
        description={`Delete device "${deleting?.hostname}"? Its collected inventory history will also be removed. This cannot be undone.`}
        pending={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
