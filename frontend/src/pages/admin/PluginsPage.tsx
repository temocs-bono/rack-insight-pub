import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import {
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  Lock,
  PlugZap,
  Plus,
  RefreshCw,
  Trash2,
  XCircle,
} from "lucide-react";
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
import { usePlugins } from "@/hooks/queries";
import { api, ApiError } from "@/services/api";
import { toast } from "@/stores/toast";
import type { Plugin, PluginStatus } from "@/types";

function PluginStatusBadge({ status }: { status: PluginStatus }) {
  if (status === "HEALTHY")
    return (
      <Badge variant="success">
        <CheckCircle2 className="h-3 w-3" /> Healthy
      </Badge>
    );
  if (status === "UNHEALTHY")
    return (
      <Badge variant="critical">
        <XCircle className="h-3 w-3" /> Unhealthy
      </Badge>
    );
  if (status === "DISABLED")
    return (
      <Badge variant="muted">
        <Lock className="h-3 w-3" /> Disabled
      </Badge>
    );
  return (
    <Badge variant="warning">
      <HelpCircle className="h-3 w-3" /> Unknown
    </Badge>
  );
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-gray-100 py-1.5 text-sm">
      <span className="text-gray-500">{label}</span>
      <span className="min-w-0 truncate text-right font-medium text-gray-800">{value}</span>
    </div>
  );
}

const EMPTY_FORM = { name: "", endpoint: "", display_name: "" };

export function PluginsPage() {
  const { data: plugins, isLoading } = usePlugins();
  const queryClient = useQueryClient();
  const [registerOpen, setRegisterOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [detail, setDetail] = useState<Plugin | null>(null);
  const [deleting, setDeleting] = useState<Plugin | null>(null);

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["plugins"] });

  const register = useMutation({
    mutationFn: () =>
      api.createPlugin({
        name: form.name,
        endpoint: form.endpoint,
        display_name: form.display_name || null,
      }),
    onSuccess: () => {
      toast.success("Plugin registered", form.name);
      setRegisterOpen(false);
      setForm(EMPTY_FORM);
      invalidate();
    },
    onError: (err) =>
      toast.error("Register failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const toggleEnabled = useMutation({
    mutationFn: (plugin: Plugin) =>
      api.updatePlugin(plugin.id, { enabled: !plugin.enabled }),
    onSuccess: (p) => {
      toast.success(p.enabled ? "Plugin enabled" : "Plugin disabled", p.name);
      invalidate();
    },
    onError: (err) =>
      toast.error("Update failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const healthCheck = useMutation({
    mutationFn: (plugin: Plugin) => api.pluginHealthCheck(plugin.id),
    onSuccess: (p) => {
      toast.success("Health checked", `${p.name}: ${p.status}`);
      invalidate();
      setDetail((d) => (d && d.id === p.id ? p : d));
    },
    onError: (err) =>
      toast.error("Health check failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deletePlugin(id),
    onSuccess: () => {
      toast.success("Plugin removed", deleting?.name);
      setDeleting(null);
      invalidate();
    },
    onError: (err) =>
      toast.error("Delete failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const columns = useMemo<ColumnDef<Plugin, unknown>[]>(
    () => [
      {
        accessorKey: "display_name",
        header: "Plugin",
        cell: ({ row }) => (
          <button
            type="button"
            onClick={() => setDetail(row.original)}
            className="flex flex-col items-start text-left"
          >
            <span className="font-medium text-blue-700 hover:underline">
              {row.original.display_name}
            </span>
            <span className="text-xs text-gray-400">{row.original.name}</span>
          </button>
        ),
      },
      {
        accessorKey: "version",
        header: "Version",
        cell: ({ row }) => (
          <span className="text-sm">
            {row.original.version ?? "-"}
            <span className="ml-1 text-xs text-gray-400">({row.original.api_version})</span>
          </span>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => <PluginStatusBadge status={row.original.status} />,
      },
      {
        accessorKey: "endpoint",
        header: "Endpoint",
        cell: (c) => (
          <code className="text-xs text-gray-600">{c.getValue() as string}</code>
        ),
      },
      {
        accessorKey: "last_health_check",
        header: "Last Check",
        cell: (c) =>
          c.getValue() ? new Date(String(c.getValue())).toLocaleString() : "Never",
      },
      {
        accessorKey: "enabled",
        header: "Enabled",
        cell: ({ row }) => (
          <Badge variant={row.original.enabled ? "success" : "muted"}>
            {row.original.enabled ? "Yes" : "No"}
          </Badge>
        ),
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <PermissionGate permission="plugin.view">
              <Button
                variant="ghost"
                size="icon"
                title="Health check"
                disabled={healthCheck.isPending}
                onClick={() => healthCheck.mutate(row.original)}
              >
                <RefreshCw className="h-4 w-4 text-gray-500" />
              </Button>
            </PermissionGate>
            <PermissionGate permission="plugin.manage">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => toggleEnabled.mutate(row.original)}
              >
                {row.original.enabled ? "Disable" : "Enable"}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                title={
                  row.original.managed_by_config
                    ? "Config-managed plugins are re-added on restart"
                    : "Remove"
                }
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
    [healthCheck.isPending],
  );

  return (
    <div className="flex flex-col gap-4">
      <Breadcrumb crumbs={[{ label: "Administration" }, { label: "Plugins" }]} />
      <p className="text-sm text-gray-500">
        Plugins are independent backend services registered with the Core. A plugin being
        unhealthy never affects Rack Insight itself. Config-declared plugins are re-registered
        automatically on startup.
      </p>

      <DataTable
        data={plugins ?? []}
        columns={columns}
        isLoading={isLoading}
        searchPlaceholder="Search plugins…"
        toolbar={
          <PermissionGate permission="plugin.manage">
            <Button onClick={() => setRegisterOpen(true)}>
              <Plus className="h-4 w-4" /> Register Plugin
            </Button>
          </PermissionGate>
        }
        emptyState={
          <EmptyState
            Icon={PlugZap}
            title="No plugins registered"
            description="Register a plugin by endpoint, or declare it in the Core's PLUGINS_CONFIG."
          />
        }
      />

      {/* Register */}
      <Dialog
        open={registerOpen}
        onClose={() => setRegisterOpen(false)}
        title="Register Plugin"
        footer={
          <>
            <Button variant="outline" onClick={() => setRegisterOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => register.mutate()}
              disabled={register.isPending || !form.name || !form.endpoint}
            >
              {register.isPending ? "Registering…" : "Register"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <Field label="Name *">
            <Input
              value={form.name}
              autoFocus
              placeholder="example-plugin"
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Endpoint * (service DNS)">
            <Input
              value={form.endpoint}
              placeholder="http://example-plugin:8080"
              onChange={(e) => setForm({ ...form, endpoint: e.target.value })}
            />
          </Field>
          <Field label="Display Name">
            <Input
              value={form.display_name}
              placeholder="Example Plugin"
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            />
          </Field>
        </div>
      </Dialog>

      {/* Detail */}
      <Dialog
        open={detail !== null}
        onClose={() => setDetail(null)}
        title={detail ? detail.display_name : "Plugin"}
        description={detail?.description ?? undefined}
        footer={
          detail && (
            <PermissionGate permission="plugin.view">
              <Button
                variant="outline"
                disabled={healthCheck.isPending}
                onClick={() => healthCheck.mutate(detail)}
              >
                <RefreshCw className="h-4 w-4" /> Health Check
              </Button>
            </PermissionGate>
          )
        }
      >
        {detail && (
          <div className="flex flex-col gap-1">
            <DetailRow label="Name" value={detail.name} />
            <DetailRow label="Version" value={detail.version ?? "-"} />
            <DetailRow label="API Version" value={detail.api_version} />
            <DetailRow label="Status" value={<PluginStatusBadge status={detail.status} />} />
            <DetailRow label="Endpoint" value={<code className="text-xs">{detail.endpoint}</code>} />
            <DetailRow
              label="Managed by config"
              value={detail.managed_by_config ? "Yes" : "No"}
            />
            <DetailRow
              label="Last Check"
              value={
                detail.last_health_check
                  ? new Date(detail.last_health_check).toLocaleString()
                  : "Never"
              }
            />
            <DetailRow
              label="Last Success"
              value={
                detail.last_success_at
                  ? new Date(detail.last_success_at).toLocaleString()
                  : "-"
              }
            />
            <DetailRow
              label="Last Failure"
              value={
                detail.last_failure_at
                  ? new Date(detail.last_failure_at).toLocaleString()
                  : "-"
              }
            />
            {detail.failure_reason && (
              <div className="mt-2 flex items-start gap-2 rounded-md border border-orange-300 bg-orange-50 p-2 text-sm text-orange-800">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span className="min-w-0 break-words">{detail.failure_reason}</span>
              </div>
            )}
          </div>
        )}
      </Dialog>

      <ConfirmDialog
        open={deleting !== null}
        title="Remove Plugin"
        confirmLabel="Remove"
        description={
          deleting?.managed_by_config
            ? `"${deleting?.name}" is declared in PLUGINS_CONFIG and will be re-registered on the next Core restart. Remove anyway?`
            : `Remove plugin "${deleting?.name}" from the registry?`
        }
        pending={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
