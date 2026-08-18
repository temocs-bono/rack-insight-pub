import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Search as SearchIcon } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Breadcrumb } from "@/components/Breadcrumb";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useClusterRacks, useClusters } from "@/hooks/queries";
import { api } from "@/services/api";

const PAGE_SIZE = 25;
const STATUSES = ["", "ONLINE", "WARNING", "OFFLINE", "UNKNOWN"] as const;

export function SearchPage() {
  const [q, setQ] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [clusterId, setClusterId] = useState("");
  const [rackId, setRackId] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);

  const { data: clusters } = useClusters();
  const { data: racks } = useClusterRacks(clusterId);

  const { data: results, isLoading } = useQuery({
    queryKey: ["devices", "search", submitted, clusterId, rackId, status, page],
    queryFn: () =>
      api.searchDevices({
        q: submitted,
        cluster_id: clusterId || undefined,
        rack_id: rackId || undefined,
        status: status || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
  });

  const totalPages = results ? Math.max(1, Math.ceil(results.total / PAGE_SIZE)) : 1;

  const applyFilters = () => {
    setSubmitted(q);
    setPage(1);
  };

  return (
    <div className="flex flex-col gap-4">
      <Breadcrumb crumbs={[{ label: "Inventory Search" }]} />

      <div className="flex flex-wrap items-end gap-3">
        <Field label="Search (hostname / serial / vendor / model)">
          <div className="flex gap-2">
            <Input
              className="w-80"
              placeholder="e.g. smf-worker, DL380, PZ1234…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && applyFilters()}
            />
            <Button onClick={applyFilters}>
              <SearchIcon className="h-4 w-4" /> Search
            </Button>
          </div>
        </Field>
        <Field label="Cluster">
          <Select
            className="w-44"
            value={clusterId}
            onChange={(e) => {
              setClusterId(e.target.value);
              setRackId("");
              setPage(1);
            }}
          >
            <option value="">All clusters</option>
            {clusters?.map((cluster) => (
              <option key={cluster.id} value={cluster.id}>
                {cluster.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Rack">
          <Select
            className="w-44"
            value={rackId}
            disabled={!clusterId}
            onChange={(e) => {
              setRackId(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All racks</option>
            {racks?.map((rack) => (
              <option key={rack.id} value={rack.id}>
                {rack.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Status">
          <Select
            className="w-36"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {value || "All statuses"}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : !results || results.items.length === 0 ? (
        <EmptyState
          Icon={SearchIcon}
          title="No matching devices"
          description="Adjust the search text or filters and try again."
        />
      ) : (
        <>
          <Table>
            <THead>
              <TR>
                <TH>Hostname</TH>
                <TH>Type</TH>
                <TH>Vendor</TH>
                <TH>Model</TH>
                <TH>Management IP</TH>
                <TH>Cluster</TH>
                <TH>Rack</TH>
                <TH>Status</TH>
              </TR>
            </THead>
            <TBody>
              {results.items.map((device) => (
                <TR key={device.id}>
                  <TD>
                    <Link
                      to={`/devices/${device.id}`}
                      className="font-medium text-blue-600 hover:underline"
                    >
                      {device.display_name ?? device.hostname}
                    </Link>
                  </TD>
                  <TD>{device.device_type}</TD>
                  <TD>{device.vendor ?? "-"}</TD>
                  <TD>{device.model ?? "-"}</TD>
                  <TD className="font-mono text-xs">{device.management_ip ?? "-"}</TD>
                  <TD>{device.cluster_name ?? "-"}</TD>
                  <TD>
                    {device.rack_name ? (
                      <Link
                        to={`/racks/${device.rack_id}`}
                        className="text-blue-600 hover:underline"
                      >
                        {device.rack_name}
                      </Link>
                    ) : (
                      "-"
                    )}
                  </TD>
                  <TD>
                    <StatusBadge status={device.status} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>
              {results.total} devices · page {results.page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft className="h-4 w-4" /> Prev
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
