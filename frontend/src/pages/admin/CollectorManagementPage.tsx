import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, ChevronDown, ChevronRight, Play } from "lucide-react";
import { Fragment, useState } from "react";
import { Breadcrumb } from "@/components/Breadcrumb";
import { EmptyState } from "@/components/EmptyState";
import { HealthBadge } from "@/components/HealthBadge";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useCollectorStatus } from "@/hooks/queries";
import { api, ApiError } from "@/services/api";
import { toast } from "@/stores/toast";
import type { CollectorDeviceStatus } from "@/types";

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "-";
}

function CollectorLogRows({ deviceId }: { deviceId: string }) {
  const { data: logs, isLoading } = useQuery({
    queryKey: ["collector", "logs", deviceId],
    queryFn: () => api.collectorLogs(deviceId),
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-1 p-3">
        <Skeleton className="h-5 w-full" />
        <Skeleton className="h-5 w-full" />
      </div>
    );
  }
  if (!logs || logs.length === 0) {
    return <p className="p-3 text-xs text-gray-500">No collector runs recorded yet.</p>;
  }
  return (
    <div className="max-h-64 overflow-y-auto p-3">
      <table className="w-full text-xs">
        <tbody className="divide-y divide-gray-100">
          {logs.map((log) => (
            <tr key={log.id}>
              <td className="whitespace-nowrap py-1.5 pr-3 text-gray-500">
                {formatTime(log.created_at)}
              </td>
              <td className="py-1.5 pr-3">
                <Badge variant={log.success ? "success" : "critical"}>
                  {log.success ? "Success" : "Failed"}
                </Badge>
                {log.error_code && (
                  <Badge variant="warning" className="ml-1 font-mono">
                    {log.error_code}
                  </Badge>
                )}
              </td>
              <td className="whitespace-nowrap py-1.5 pr-3 text-gray-500">
                {log.duration_ms} ms
              </td>
              <td className="py-1.5 pr-3 text-gray-500">{log.trigger ?? "-"}</td>
              <td className="break-all py-1.5 text-gray-600">
                {log.readable_message ?? log.message ?? "-"}
                {log.readable_message && log.message && (
                  <span className="block text-[11px] text-gray-400">{log.message}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CollectorManagementPage() {
  const { data: statuses, isLoading } = useCollectorStatus();
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [collecting, setCollecting] = useState<string | null>(null);

  const collectNow = useMutation({
    mutationFn: (deviceId: string) => {
      setCollecting(deviceId);
      return api.refreshDevice(deviceId);
    },
    onSuccess: (_data, deviceId) => {
      toast.success("Collection finished", "Snapshot saved successfully");
      void queryClient.invalidateQueries({ queryKey: ["collector"] });
      void queryClient.invalidateQueries({ queryKey: ["device", deviceId] });
    },
    onError: (err) =>
      toast.error(
        "Collection failed",
        err instanceof ApiError ? err.message : "Unexpected error",
      ),
    onSettled: () => setCollecting(null),
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3">
        <Breadcrumb
          crumbs={[{ label: "Administration" }, { label: "Collector Management" }]}
        />
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Breadcrumb
        crumbs={[{ label: "Administration" }, { label: "Collector Management" }]}
      />

      {!statuses || statuses.length === 0 ? (
        <EmptyState
          Icon={Activity}
          title="No devices registered"
          description="Register devices in Device Management to run collectors against them."
        />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH className="w-8" />
              <TH>Device</TH>
              <TH>Location</TH>
              <TH>Status</TH>
              <TH>Health Score</TH>
              <TH>Last Snapshot</TH>
              <TH>Last Success</TH>
              <TH>Last Failure</TH>
              <TH className="w-36" />
            </TR>
          </THead>
          <TBody>
            {statuses.map((entry: CollectorDeviceStatus) => (
              <Fragment key={entry.device_id}>
                <TR>
                  <TD>
                    <button
                      type="button"
                      onClick={() =>
                        setExpanded(expanded === entry.device_id ? null : entry.device_id)
                      }
                      className="text-gray-400 hover:text-gray-600"
                      aria-label="Show collector log"
                    >
                      {expanded === entry.device_id ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                    </button>
                  </TD>
                  <TD>
                    <span className="font-medium">
                      {entry.display_name ?? entry.hostname}
                    </span>
                    <span className="ml-2 text-xs text-gray-400">{entry.device_type}</span>
                  </TD>
                  <TD className="text-xs text-gray-500">
                    {entry.cluster_name ?? "-"} / {entry.rack_name ?? "-"}
                  </TD>
                  <TD>
                    <StatusBadge
                      status={collecting === entry.device_id ? "REFRESHING" : entry.status}
                    />
                  </TD>
                  <TD>
                    <HealthBadge score={entry.health_score} label={entry.health_label} />
                  </TD>
                  <TD className="text-xs text-gray-500">
                    {formatTime(entry.last_snapshot_at)}
                  </TD>
                  <TD className="text-xs text-gray-500">
                    {formatTime(entry.last_success_at)}
                  </TD>
                  <TD className="text-xs">
                    <span className="text-gray-500">{formatTime(entry.last_failure_at)}</span>
                    {entry.last_error_code && (
                      <Badge variant="warning" className="ml-1 font-mono text-[10px]">
                        {entry.last_error_code}
                      </Badge>
                    )}
                    {(entry.last_error_readable ?? entry.last_error) && (
                      <p
                        className="max-w-56 truncate text-red-500"
                        title={entry.last_error ?? undefined}
                      >
                        {entry.last_error_readable ?? entry.last_error}
                      </p>
                    )}
                  </TD>
                  <TD>
                    <Button
                      size="sm"
                      onClick={() => collectNow.mutate(entry.device_id)}
                      disabled={collecting !== null}
                    >
                      <Play className="h-3.5 w-3.5" />
                      {collecting === entry.device_id ? "Collecting…" : "Collect Now"}
                    </Button>
                  </TD>
                </TR>
                {expanded === entry.device_id && (
                  <TR className="bg-gray-50 hover:bg-gray-50">
                    <TD colSpan={9} className="p-0">
                      <CollectorLogRows deviceId={entry.device_id} />
                    </TD>
                  </TR>
                )}
              </Fragment>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
