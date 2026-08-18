import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellOff, CheckCheck, Eye } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertSeverityBadge, AlertStatusBadge } from "@/components/AlertBadges";
import { Breadcrumb } from "@/components/Breadcrumb";
import { DiffViewer } from "@/components/DiffViewer";
import { EmptyState } from "@/components/EmptyState";
import { PermissionGate } from "@/components/PermissionGate";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useClusters } from "@/hooks/queries";
import { api, ApiError } from "@/services/api";
import { markAlertsSeen } from "@/stores/alertsSeen";
import { toast } from "@/stores/toast";
import type { Alert } from "@/types";

// Operational domains (Alert.category), the axis the UI filters by. The
// underlying event type (what happened) is shown per-row as a subtitle.
const CATEGORIES = [
  "Hardware",
  "Firmware",
  "Connectivity",
  "Collector",
  "Credential",
  "Health",
];

const PAGE_SIZE = 25;

interface Filters {
  severity: string;
  status: string;
  category: string;
  cluster_id: string;
  hostname: string;
  vendor: string;
  model: string;
  q: string;
  date_from: string;
  date_to: string;
}

const EMPTY_FILTERS: Filters = {
  severity: "",
  status: "",
  category: "",
  cluster_id: "",
  hostname: "",
  vendor: "",
  model: "",
  q: "",
  date_from: "",
  date_to: "",
};

export function AlertsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: clusters } = useClusters();
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [viewing, setViewing] = useState<Alert | null>(null);

  // Opening the Alert Center clears the header's unread badge.
  useEffect(() => {
    markAlertsSeen();
  }, []);

  const { data, isLoading } = useQuery({
    queryKey: ["alerts", filters, page],
    queryFn: () =>
      api.alerts({
        ...filters,
        date_from: filters.date_from ? `${filters.date_from}T00:00:00` : "",
        date_to: filters.date_to ? `${filters.date_to}T23:59:59` : "",
        page,
        page_size: PAGE_SIZE,
      }),
    refetchInterval: 30_000,
  });

  const resolve = useMutation({
    mutationFn: (id: string) => api.resolveAlert(id),
    onSuccess: () => {
      toast.success("Alert resolved");
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err) =>
      toast.error(
        "Resolve failed",
        err instanceof ApiError ? err.message : "Unexpected error",
      ),
  });

  const set = (key: keyof Filters) => (value: string) => {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="flex flex-col gap-4">
      <Breadcrumb crumbs={[{ label: "Alerts" }, { label: "Alert Center" }]} />

      <div className="grid grid-cols-2 gap-2 rounded-lg border border-gray-200 bg-white p-3 md:grid-cols-5">
        <Select value={filters.severity} onChange={(e) => set("severity")(e.target.value)}>
          <option value="">All severities</option>
          <option value="CRITICAL">Critical</option>
          <option value="WARNING">Warning</option>
          <option value="INFO">Info</option>
        </Select>
        <Select value={filters.status} onChange={(e) => set("status")(e.target.value)}>
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="RESOLVED">Resolved</option>
        </Select>
        <Select value={filters.category} onChange={(e) => set("category")(e.target.value)}>
          <option value="">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
        <Select
          value={filters.cluster_id}
          onChange={(e) => set("cluster_id")(e.target.value)}
        >
          <option value="">All clusters</option>
          {(clusters ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </Select>
        <Input
          placeholder="Hostname…"
          value={filters.hostname}
          onChange={(e) => set("hostname")(e.target.value)}
        />
        <Input
          placeholder="Vendor…"
          value={filters.vendor}
          onChange={(e) => set("vendor")(e.target.value)}
        />
        <Input
          placeholder="Model…"
          value={filters.model}
          onChange={(e) => set("model")(e.target.value)}
        />
        <Input
          placeholder="Search message…"
          value={filters.q}
          onChange={(e) => set("q")(e.target.value)}
        />
        <Input
          type="date"
          value={filters.date_from}
          onChange={(e) => set("date_from")(e.target.value)}
        />
        <Input
          type="date"
          value={filters.date_to}
          onChange={(e) => set("date_to")(e.target.value)}
        />
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          Icon={BellOff}
          title="No alerts"
          description="Alerts appear here when the Event Engine detects hardware changes, firmware changes, or state problems."
        />
      ) : (
        <>
          <Table>
            <THead>
              <TR>
                <TH>Severity</TH>
                <TH>Status</TH>
                <TH>Category</TH>
                <TH>Cluster</TH>
                <TH>Rack</TH>
                <TH>Hostname</TH>
                <TH>Message</TH>
                <TH>Created</TH>
                <TH>Resolved</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {data.items.map((alert) => (
                <TR
                  key={alert.id}
                  className="cursor-pointer hover:bg-gray-50"
                  onClick={() => navigate(`/devices/${alert.device_id}`)}
                >
                  <TD>
                    <AlertSeverityBadge severity={alert.severity} />
                  </TD>
                  <TD>
                    <AlertStatusBadge status={alert.status} />
                  </TD>
                  <TD>
                    <div className="flex flex-col gap-0.5">
                      <Badge variant="muted">{alert.category}</Badge>
                      <span className="text-[11px] text-gray-400">{alert.event_type}</span>
                    </div>
                  </TD>
                  <TD>{alert.cluster_name ?? "-"}</TD>
                  <TD>{alert.rack_name ?? "-"}</TD>
                  <TD className="font-medium text-blue-700">{alert.hostname}</TD>
                  <TD className="max-w-md truncate" title={alert.message}>
                    {alert.message}
                  </TD>
                  <TD className="whitespace-nowrap text-xs">
                    {new Date(alert.created_at).toLocaleString()}
                  </TD>
                  <TD className="whitespace-nowrap text-xs">
                    {alert.resolved_at
                      ? new Date(alert.resolved_at).toLocaleString()
                      : "-"}
                  </TD>
                  <TD onClick={(e) => e.stopPropagation()}>
                    <div className="flex justify-end gap-1">
                      {alert.changes.length > 0 && (
                        <Button
                          variant="ghost"
                          size="icon"
                          title="View changes"
                          onClick={() => setViewing(alert)}
                        >
                          <Eye className="h-4 w-4 text-gray-500" />
                        </Button>
                      )}
                      {alert.status === "ACTIVE" && (
                        <PermissionGate permission="alert.resolve">
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Resolve"
                            disabled={resolve.isPending}
                            onClick={() => resolve.mutate(alert.id)}
                          >
                            <CheckCheck className="h-4 w-4 text-green-600" />
                          </Button>
                        </PermissionGate>
                      )}
                    </div>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>

          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>
              {data.total} alert{data.total !== 1 ? "s" : ""}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <span>
                Page {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}

      <Dialog
        open={viewing !== null}
        onClose={() => setViewing(null)}
        title={viewing ? `Changes — ${viewing.hostname}` : "Changes"}
        description={viewing?.message}
        className="max-w-2xl"
      >
        {viewing && <DiffViewer changes={viewing.changes} />}
      </Dialog>
    </div>
  );
}
