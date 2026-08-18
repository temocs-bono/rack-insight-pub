import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  BellRing,
  Boxes,
  CheckCircle2,
  Cpu,
  Info,
  Network,
  OctagonAlert,
  Plus,
  Server as ServerIcon,
  Wrench,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertSeverityBadge, AlertStatusBadge } from "@/components/AlertBadges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Breadcrumb } from "@/components/Breadcrumb";
import { EmptyState } from "@/components/EmptyState";
import { ExportMenu } from "@/components/ExportMenu";
import { HistoryCard } from "@/components/HistoryCard";
import { PermissionGate } from "@/components/PermissionGate";
import { useClusters, useDashboardAlerts } from "@/hooks/queries";
import { api, ApiError } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import { toast } from "@/stores/toast";
import type { Alert, HistoryEntry } from "@/types";

function StatCard({
  title,
  value,
  Icon,
  tone,
  onClick,
}: {
  title: string;
  value: number | undefined;
  Icon: LucideIcon;
  tone: string;
  onClick?: () => void;
}) {
  return (
    <Card
      className={onClick ? "cursor-pointer transition-shadow hover:shadow-md" : undefined}
      onClick={onClick}
    >
      <CardContent className="flex items-center gap-3 p-4">
        <Icon className={`h-7 w-7 ${tone}`} />
        <div>
          <p className="text-2xl font-semibold leading-tight">{value ?? "–"}</p>
          <p className="text-xs uppercase tracking-wide text-gray-400">{title}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function AlertRow({ alert }: { alert: Alert }) {
  return (
    <Link
      to={`/devices/${alert.device_id}`}
      className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-gray-50"
    >
      <AlertSeverityBadge severity={alert.severity} />
      <AlertStatusBadge status={alert.status} />
      <span className="font-medium text-blue-700">{alert.hostname}</span>
      <span className="min-w-0 flex-1 truncate text-gray-600" title={alert.message}>
        {alert.message}
      </span>
      <span className="shrink-0 text-xs text-gray-400">
        {new Date(alert.created_at).toLocaleString()}
      </span>
    </Link>
  );
}

function ChangesCard({
  title,
  Icon,
  entries,
}: {
  title: string;
  Icon: LucideIcon;
  entries: HistoryEntry[] | undefined;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <Icon className="h-4 w-4 text-blue-600" /> {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {!entries || entries.length === 0 ? (
          <p className="text-sm text-gray-400">Nothing recorded recently.</p>
        ) : (
          entries.map((entry) => (
            <HistoryCard key={entry.id} entry={entry} showHostname />
          ))
        )}
      </CardContent>
    </Card>
  );
}

export function DashboardPage() {
  const { data: clusters, isLoading } = useClusters();
  const { data: ops } = useDashboardAlerts();
  const { hasPermission } = useAuthStore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({ name: "", site: "", vendor: "" });

  const createCluster = useMutation({
    mutationFn: () =>
      api.createCluster({
        name: form.name,
        site: form.site || null,
        vendor: form.vendor || null,
      }),
    onSuccess: (cluster) => {
      toast.success("Cluster created", form.name);
      setCreateOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["clusters"] });
      navigate(`/clusters/${cluster.id}`);
    },
    onError: (err) =>
      toast.error(
        "Create failed",
        err instanceof ApiError ? err.message : "Unexpected error",
      ),
  });

  const canSeeAlerts = hasPermission("alert.view");
  const canCreateCluster = hasPermission("cluster.create");
  const goToAlerts = canSeeAlerts ? () => navigate("/alerts") : undefined;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <Breadcrumb crumbs={[{ label: "Operations Dashboard" }]} />
        <ExportMenu scope="all" label="Export All" />
      </div>

      {canSeeAlerts && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
            <StatCard
              title="Critical Alerts"
              value={ops?.active_critical}
              Icon={OctagonAlert}
              tone="text-red-600"
              onClick={goToAlerts}
            />
            <StatCard
              title="Warning Alerts"
              value={ops?.active_warning}
              Icon={AlertTriangle}
              tone="text-orange-500"
              onClick={goToAlerts}
            />
            <StatCard
              title="Info Alerts"
              value={ops?.active_info}
              Icon={Info}
              tone="text-blue-500"
              onClick={goToAlerts}
            />
            <StatCard
              title="Offline Devices"
              value={ops?.offline_devices}
              Icon={XCircle}
              tone="text-red-500"
            />
            <StatCard
              title="Healthy Devices"
              value={ops?.healthy_devices}
              Icon={CheckCircle2}
              tone="text-green-600"
            />
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2">
                    <BellRing className="h-4 w-4 text-blue-600" /> Latest Alerts
                  </span>
                  <Link to="/alerts" className="text-xs font-normal text-blue-600 hover:underline">
                    Alert Center →
                  </Link>
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col">
                {!ops || ops.latest_alerts.length === 0 ? (
                  <p className="text-sm text-gray-400">No alerts. All quiet.</p>
                ) : (
                  ops.latest_alerts.map((alert) => <AlertRow key={alert.id} alert={alert} />)
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <OctagonAlert className="h-4 w-4 text-red-600" /> Critical Devices
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col">
                {!ops || ops.critical_devices.length === 0 ? (
                  <p className="text-sm text-gray-400">No devices in critical state.</p>
                ) : (
                  ops.critical_devices.map((alert) => (
                    <AlertRow key={alert.id} alert={alert} />
                  ))
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <ChangesCard
              title="Recent Hardware Changes"
              Icon={Cpu}
              entries={ops?.recent_hardware_changes}
            />
            <ChangesCard
              title="Recent Firmware Changes"
              Icon={Wrench}
              entries={ops?.recent_firmware_changes}
            />
          </div>
        </>
      )}

      <h2 className="mt-2 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-400">
        <Boxes className="h-4 w-4" /> Clusters
      </h2>
      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      ) : clusters?.length === 0 ? (
        <EmptyState
          Icon={Boxes}
          title="No clusters yet"
          description={
            canCreateCluster
              ? "Create your first cluster, then add racks and register devices — all from the web UI."
              : "No clusters have been configured yet. Ask an administrator to create one."
          }
          action={
            canCreateCluster ? (
              <Button onClick={() => setCreateOpen(true)}>
                <Plus className="h-4 w-4" /> Create Cluster
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {clusters?.map((cluster) => (
            <motion.div key={cluster.id} whileHover={{ scale: 1.01 }}>
              <Card
                className="cursor-pointer transition-shadow hover:shadow-md"
                onClick={() => navigate(`/clusters/${cluster.id}`)}
              >
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2">
                      <Boxes className="h-5 w-5 text-blue-600" />
                      {cluster.name}
                    </CardTitle>
                    {cluster.vendor && <Badge variant="muted">{cluster.vendor}</Badge>}
                  </div>
                </CardHeader>
                <CardContent className="grid grid-cols-3 gap-2 text-sm">
                  <div className="flex items-center gap-1 text-gray-600">
                    <Boxes className="h-4 w-4" /> {cluster.rack_count} Racks
                  </div>
                  <div className="flex items-center gap-1 text-gray-600">
                    <ServerIcon className="h-4 w-4" /> {cluster.server_count} Servers
                  </div>
                  <div className="flex items-center gap-1 text-gray-600">
                    <Network className="h-4 w-4" /> {cluster.switch_count} Switches
                  </div>
                  <div className="col-span-3 mt-2 flex items-center gap-2">
                    <Badge variant="success">{cluster.online_count} Online</Badge>
                    {cluster.warning_count > 0 && (
                      <Badge variant="warning">{cluster.warning_count} Warning</Badge>
                    )}
                    <span className="ml-auto text-xs text-gray-400">
                      {cluster.last_refresh
                        ? `Refreshed ${new Date(cluster.last_refresh).toLocaleString()}`
                        : "Never refreshed"}
                    </span>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>
      )}

      <PermissionGate permission="cluster.create">
        <Dialog
          open={createOpen}
          onClose={() => setCreateOpen(false)}
          title="Create Cluster"
          footer={
            <>
              <Button variant="outline" onClick={() => setCreateOpen(false)}>
                Cancel
              </Button>
              <Button
                onClick={() => createCluster.mutate()}
                disabled={!form.name || createCluster.isPending}
              >
                {createCluster.isPending ? "Creating…" : "Create"}
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
          </div>
        </Dialog>
      </PermissionGate>
    </div>
  );
}
