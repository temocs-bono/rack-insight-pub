import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Radar, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { Breadcrumb } from "@/components/Breadcrumb";
import { EmptyState } from "@/components/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useClusterRacks, useClusters, useDeviceTemplates } from "@/hooks/queries";
import { api, ApiError } from "@/services/api";
import { toast } from "@/stores/toast";
import type { DiscoveredDevice } from "@/types";

interface ImportRow {
  discovered_id: string;
  hostname: string;
  management_ip: string;
  selected: boolean;
}

export function DiscoveryPage() {
  const queryClient = useQueryClient();
  const { data: discoveries, isLoading } = useQuery({
    queryKey: ["discovery"],
    queryFn: api.discoveries,
  });
  const { data: clusters } = useClusters();
  const { data: templates } = useDeviceTemplates();

  const [targets, setTargets] = useState("");
  const [community, setCommunity] = useState("public");
  const [importOpen, setImportOpen] = useState(false);
  const [clusterId, setClusterId] = useState("");
  const [rackId, setRackId] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [rows, setRows] = useState<ImportRow[]>([]);
  const { data: racks } = useClusterRacks(clusterId);

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["discovery"] });

  const scan = useMutation({
    mutationFn: () =>
      api.discoveryScan({
        targets: targets.split(/[\s,]+/).filter(Boolean),
        community,
      }),
    onSuccess: (result) => {
      toast.success(
        `Scan complete`,
        `${result.reachable} reachable of ${result.scanned} scanned`,
      );
      invalidate();
    },
    onError: (err) =>
      toast.error(
        "Scan failed",
        err instanceof ApiError ? err.message : "SNMP scan could not run",
      ),
  });

  const ignore = useMutation({
    mutationFn: (id: string) => api.ignoreDiscovery(id),
    onSuccess: invalidate,
  });

  const openImport = () => {
    const pending = (discoveries ?? []).filter((d) => d.status === "PENDING");
    setRows(
      pending.map((d) => ({
        discovered_id: d.id,
        hostname: d.sysname || d.ip_address,
        management_ip: d.ip_address,
        selected: true,
      })),
    );
    setImportOpen(true);
  };

  const runImport = useMutation({
    mutationFn: () => {
      const selected = rows.filter((r) => r.selected && r.hostname.trim());
      return api.discoveryImport({
        rack_id: rackId,
        template_id: templateId || null,
        items: selected.map((r) => ({
          discovered_id: r.discovered_id,
          hostname: r.hostname.trim(),
          management_ip: r.management_ip.trim() || null,
        })),
      });
    },
    onSuccess: async (result) => {
      if (result.errors.length > 0) {
        toast.error(
          "Import had conflicts",
          result.errors.map((e) => `${e.hostname}: ${e.error}`).join("; "),
        );
        return;
      }
      toast.success(`${result.created.length} devices imported`);
      setImportOpen(false);
      invalidate();
      void queryClient.invalidateQueries({ queryKey: ["devices"] });
      // F3 — initial collection immediately after onboarding (non-blocking).
      collectNow(result.created.map((d) => d.id));
    },
    onError: (err) =>
      toast.error("Import failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const collectNow = (deviceIds: string[]) => {
    if (deviceIds.length === 0) return;
    toast.success("Initial collection started", `${deviceIds.length} device(s)`);
    void Promise.allSettled(deviceIds.map((id) => api.refreshDevice(id))).then(() =>
      queryClient.invalidateQueries({ queryKey: ["collector"] }),
    );
  };

  const pending = (discoveries ?? []).filter((d) => d.status === "PENDING");

  return (
    <div className="flex flex-col gap-4">
      <Breadcrumb crumbs={[{ label: "Administration" }, { label: "SNMP Discovery" }]} />
      <p className="text-sm text-gray-500">
        Discover SNMP-capable infrastructure. Discovered devices are never
        installed automatically — review and import them below.
      </p>

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 bg-white p-4">
        <Field label="Targets (IPs or CIDR, comma/space separated)">
          <Input
            className="w-96"
            placeholder="10.0.1.0/28, 10.0.2.5"
            value={targets}
            onChange={(e) => setTargets(e.target.value)}
          />
        </Field>
        <Field label="SNMP Community">
          <Input
            className="w-40"
            value={community}
            onChange={(e) => setCommunity(e.target.value)}
          />
        </Field>
        <Button onClick={() => scan.mutate()} disabled={!targets.trim() || scan.isPending}>
          <Search className="h-4 w-4" /> {scan.isPending ? "Scanning…" : "Scan"}
        </Button>
        <Button
          variant="outline"
          className="ml-auto"
          disabled={pending.length === 0}
          onClick={openImport}
        >
          Import Selected…
        </Button>
      </div>

      {isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : pending.length === 0 ? (
        <EmptyState
          Icon={Radar}
          title="No pending discoveries"
          description="Run an SNMP scan to find infrastructure awaiting onboarding."
        />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>IP Address</TH>
              <TH>System Name</TH>
              <TH>Vendor</TH>
              <TH>Type</TH>
              <TH>Description</TH>
              <TH className="w-16" />
            </TR>
          </THead>
          <TBody>
            {pending.map((d: DiscoveredDevice) => (
              <TR key={d.id}>
                <TD className="font-mono text-xs">{d.ip_address}</TD>
                <TD>{d.sysname ?? "-"}</TD>
                <TD>{d.vendor ? <Badge variant="muted">{d.vendor}</Badge> : "-"}</TD>
                <TD>{d.device_type_guess ?? "-"}</TD>
                <TD className="max-w-md truncate text-xs text-gray-500" title={d.sysdescr ?? ""}>
                  {d.sysdescr ?? "-"}
                </TD>
                <TD>
                  <Button
                    variant="ghost"
                    size="icon"
                    title="Ignore"
                    onClick={() => ignore.mutate(d.id)}
                  >
                    <Trash2 className="h-4 w-4 text-gray-400" />
                  </Button>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}

      <Dialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        title="Import Discovered Devices"
        description="Choose a template and rack, review the values, then create Installed Devices and run the first collection."
        className="max-w-4xl"
        footer={
          <>
            <Button variant="outline" onClick={() => setImportOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => runImport.mutate()}
              disabled={
                !rackId || rows.every((r) => !r.selected) || runImport.isPending
              }
            >
              {runImport.isPending ? "Importing…" : "Finish & Collect"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-3 gap-3">
            <Field label="Cluster">
              <Select value={clusterId} onChange={(e) => setClusterId(e.target.value)}>
                <option value="">Select…</option>
                {clusters?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Rack">
              <Select
                value={rackId}
                disabled={!clusterId}
                onChange={(e) => setRackId(e.target.value)}
              >
                <option value="">Select…</option>
                {racks?.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Device Template">
              <Select value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
                <option value="">(None)</option>
                {templates?.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="w-8 px-2 py-1.5" />
                  <th className="px-2 py-1.5 text-left">Hostname</th>
                  <th className="px-2 py-1.5 text-left">Management IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rows.map((row, index) => (
                  <tr key={row.discovered_id}>
                    <td className="px-2 py-1">
                      <input
                        type="checkbox"
                        checked={row.selected}
                        onChange={(e) =>
                          setRows((prev) =>
                            prev.map((r, i) =>
                              i === index ? { ...r, selected: e.target.checked } : r,
                            ),
                          )
                        }
                      />
                    </td>
                    <td className="px-1 py-1">
                      <Input
                        className="h-8"
                        value={row.hostname}
                        onChange={(e) =>
                          setRows((prev) =>
                            prev.map((r, i) =>
                              i === index ? { ...r, hostname: e.target.value } : r,
                            ),
                          )
                        }
                      />
                    </td>
                    <td className="px-1 py-1">
                      <Input
                        className="h-8"
                        value={row.management_ip}
                        onChange={(e) =>
                          setRows((prev) =>
                            prev.map((r, i) =>
                              i === index ? { ...r, management_ip: e.target.value } : r,
                            ),
                          )
                        }
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
