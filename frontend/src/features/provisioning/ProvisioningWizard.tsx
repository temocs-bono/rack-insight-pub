import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Trash2, Wand2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { api, ApiError } from "@/services/api";
import { toast } from "@/stores/toast";
import type { Credential, DeviceTemplate } from "@/types";
import { incrementIpv4 } from "@/utils/ip";

interface Row {
  hostname: string;
  management_ip: string;
  ilo_ip: string;
  credential_id: string;
  u_position: string;
}

interface ProvisioningWizardProps {
  open: boolean;
  onClose: () => void;
  rackId: string;
  rackName: string;
  templates: DeviceTemplate[];
  credentials: Credential[];
  onCreated: () => void;
}

type IpMode = "manual" | "sequential";
const MAX_QUANTITY = 100;

export function ProvisioningWizard({
  open,
  onClose,
  rackId,
  rackName,
  templates,
  credentials,
  onCreated,
}: ProvisioningWizardProps) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState<1 | 2>(1);

  const [templateId, setTemplateId] = useState("");
  const [quantity, setQuantity] = useState(5);
  const [prefix, setPrefix] = useState("");
  const [mgmtMode, setMgmtMode] = useState<IpMode>("manual");
  const [mgmtStart, setMgmtStart] = useState("");
  const [iloMode, setIloMode] = useState<IpMode>("manual");
  const [iloStart, setIloStart] = useState("");
  const [defaultCredentialId, setDefaultCredentialId] = useState("");
  const [collectAfter, setCollectAfter] = useState(true);
  const [rows, setRows] = useState<Row[]>([]);

  const reset = () => {
    setStep(1);
    setTemplateId("");
    setQuantity(5);
    setPrefix("");
    setMgmtMode("manual");
    setMgmtStart("");
    setIloMode("manual");
    setIloStart("");
    setDefaultCredentialId("");
    setRows([]);
  };

  const close = () => {
    reset();
    onClose();
  };

  // Build the editable preview table. Generated values are only initial
  // values — every cell can be changed in step 2.
  const generateRows = () => {
    const next: Row[] = [];
    for (let i = 0; i < quantity; i += 1) {
      next.push({
        hostname: prefix ? `${prefix}-${i + 1}` : "",
        management_ip:
          mgmtMode === "sequential" && mgmtStart ? incrementIpv4(mgmtStart, i) : "",
        ilo_ip: iloMode === "sequential" && iloStart ? incrementIpv4(iloStart, i) : "",
        credential_id: defaultCredentialId,
        u_position: "",
      });
    }
    setRows(next);
    setStep(2);
  };

  const updateRow = (index: number, patch: Partial<Row>) =>
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));

  const credentialSlot = (credentialId: string) => {
    const credential = credentials.find((c) => c.id === credentialId);
    if (!credential) return {};
    if (credential.credential_type === "REDFISH")
      return { redfish_credential_id: credentialId };
    if (credential.credential_type === "SSH") return { ssh_credential_id: credentialId };
    return { snmp_credential_id: credentialId };
  };

  const install = useMutation({
    mutationFn: () =>
      api.bulkCreateDevices({
        rack_id: rackId,
        template_id: templateId || null,
        items: rows.map((r) => ({
          hostname: r.hostname.trim(),
          management_ip: r.management_ip.trim() || null,
          ilo_ip: r.ilo_ip.trim() || null,
          u_position: r.u_position ? Number(r.u_position) : null,
          ...credentialSlot(r.credential_id),
        })),
      }),
    onSuccess: (result) => {
      if (result.errors.length > 0) {
        toast.error(
          "Fix placement conflicts",
          result.errors.map((e) => `${e.hostname}: ${e.error}`).join("; "),
        );
        return;
      }
      const skipped =
        result.skipped.length > 0 ? ` (skipped: ${result.skipped.join(", ")})` : "";
      toast.success(`${result.created.length} devices installed`, skipped || undefined);
      void queryClient.invalidateQueries({ queryKey: ["devices"] });
      void queryClient.invalidateQueries({ queryKey: ["rack", rackId, "layout"] });
      // F3 — initial collection: fire-and-forget so the UI is not blocked.
      // Progress is visible in Collector Management.
      if (collectAfter && result.created.length > 0) {
        toast.success("Initial collection started", `${result.created.length} device(s)`);
        void Promise.allSettled(result.created.map((d) => api.refreshDevice(d.id))).then(
          () => queryClient.invalidateQueries({ queryKey: ["collector"] }),
        );
      }
      onCreated();
      close();
    },
    onError: (err) =>
      toast.error("Install failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const validRows = rows.filter((r) => r.hostname.trim());
  const hasDuplicate =
    new Set(validRows.map((r) => r.hostname.trim())).size !== validRows.length;

  const firstDuplicate = (values: string[]): string | null => {
    const seen = new Set<string>();
    for (const value of values) {
      const v = value.trim();
      if (!v) continue;
      if (seen.has(v)) return v;
      seen.add(v);
    }
    return null;
  };
  const dupMgmt = firstDuplicate(rows.map((r) => r.management_ip));
  const dupIlo = firstDuplicate(rows.map((r) => r.ilo_ip));
  const hasBlocker = hasDuplicate || dupMgmt !== null || dupIlo !== null;

  return (
    <Dialog
      open={open}
      onClose={close}
      title="Provision Multiple Devices"
      description={
        step === 1
          ? `Generate installation values for rack ${rackName}, then review every row.`
          : "Review and edit any value before installing. Rack placement (U) is optional — leave blank to place later by drag-and-drop."
      }
      className="max-w-4xl"
      footer={
        step === 1 ? (
          <>
            <Button variant="outline" onClick={close}>
              Cancel
            </Button>
            <Button onClick={generateRows} disabled={!prefix || quantity < 1}>
              <Wand2 className="h-4 w-4" /> Generate {quantity} Rows
            </Button>
          </>
        ) : (
          <>
            <Button variant="outline" onClick={() => setStep(1)}>
              <ArrowLeft className="h-4 w-4" /> Back
            </Button>
            <Button
              onClick={() => install.mutate()}
              disabled={validRows.length === 0 || hasBlocker || install.isPending}
            >
              {install.isPending
                ? "Installing…"
                : collectAfter
                  ? `Install & Collect ${validRows.length}`
                  : `Install ${validRows.length} Devices`}
              {!install.isPending && <ArrowRight className="h-4 w-4" />}
            </Button>
          </>
        )
      }
    >
      {step === 1 ? (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Device Template">
              <Select value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
                <option value="">(None)</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Quantity">
              <Input
                type="number"
                min={1}
                max={MAX_QUANTITY}
                value={quantity}
                onChange={(e) =>
                  setQuantity(
                    Math.max(1, Math.min(MAX_QUANTITY, Number(e.target.value) || 1)),
                  )
                }
              />
            </Field>
            <Field label="Hostname Prefix *">
              <Input
                value={prefix}
                autoFocus
                placeholder="e.g. worker"
                onChange={(e) => setPrefix(e.target.value)}
              />
            </Field>
            <Field label="Default Credential">
              <Select
                value={defaultCredentialId}
                onChange={(e) => setDefaultCredentialId(e.target.value)}
              >
                <option value="">(None)</option>
                {credentials.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.credential_type})
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-md border border-gray-200 p-3">
              <p className="mb-2 text-xs font-semibold uppercase text-gray-500">
                Management IP
              </p>
              <Select
                className="mb-2"
                value={mgmtMode}
                onChange={(e) => setMgmtMode(e.target.value as IpMode)}
              >
                <option value="manual">Manual (enter per row)</option>
                <option value="sequential">Generate sequential</option>
              </Select>
              {mgmtMode === "sequential" && (
                <Input
                  placeholder="Start e.g. 10.10.1.100"
                  value={mgmtStart}
                  onChange={(e) => setMgmtStart(e.target.value)}
                />
              )}
            </div>
            <div className="rounded-md border border-gray-200 p-3">
              <p className="mb-2 text-xs font-semibold uppercase text-gray-500">iLO IP</p>
              <Select
                className="mb-2"
                value={iloMode}
                onChange={(e) => setIloMode(e.target.value as IpMode)}
              >
                <option value="manual">Manual (enter per row)</option>
                <option value="sequential">Generate sequential</option>
              </Select>
              {iloMode === "sequential" && (
                <Input
                  placeholder="Start e.g. 10.20.1.100"
                  value={iloStart}
                  onChange={(e) => setIloStart(e.target.value)}
                />
              )}
            </div>
          </div>
          <p className="text-xs text-gray-500">
            Sequential addressing is optional and only fills initial values — you
            can change any address in the next step.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {hasDuplicate && (
            <p className="text-xs text-red-600">
              Duplicate hostnames detected — make each hostname unique.
            </p>
          )}
          {dupMgmt && (
            <p className="text-xs text-red-600">
              Duplicate Management IP {dupMgmt} — each address must be unique.
            </p>
          )}
          {dupIlo && (
            <p className="text-xs text-red-600">
              Duplicate iLO IP {dupIlo} — each address must be unique.
            </p>
          )}
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={collectAfter}
              onChange={(e) => setCollectAfter(e.target.checked)}
            />
            Run initial inventory collection immediately after install
          </label>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-2 py-1.5 text-left">Hostname</th>
                  <th className="px-2 py-1.5 text-left">Management IP</th>
                  <th className="px-2 py-1.5 text-left">iLO IP</th>
                  <th className="px-2 py-1.5 text-left">Credential</th>
                  <th className="w-20 px-2 py-1.5 text-left">U</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rows.map((row, index) => (
                  <tr key={index}>
                    <td className="px-1 py-1">
                      <Input
                        className="h-8"
                        value={row.hostname}
                        onChange={(e) => updateRow(index, { hostname: e.target.value })}
                      />
                    </td>
                    <td className="px-1 py-1">
                      <Input
                        className="h-8"
                        value={row.management_ip}
                        onChange={(e) =>
                          updateRow(index, { management_ip: e.target.value })
                        }
                      />
                    </td>
                    <td className="px-1 py-1">
                      <Input
                        className="h-8"
                        value={row.ilo_ip}
                        onChange={(e) => updateRow(index, { ilo_ip: e.target.value })}
                      />
                    </td>
                    <td className="px-1 py-1">
                      <Select
                        className="h-8"
                        value={row.credential_id}
                        onChange={(e) =>
                          updateRow(index, { credential_id: e.target.value })
                        }
                      >
                        <option value="">(None)</option>
                        {credentials.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </Select>
                    </td>
                    <td className="px-1 py-1">
                      <Input
                        className="h-8"
                        type="number"
                        min={1}
                        placeholder="—"
                        value={row.u_position}
                        onChange={(e) => updateRow(index, { u_position: e.target.value })}
                      />
                    </td>
                    <td className="px-1 py-1">
                      <button
                        type="button"
                        className="text-gray-400 hover:text-red-500"
                        onClick={() =>
                          setRows((prev) => prev.filter((_, i) => i !== index))
                        }
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Dialog>
  );
}
