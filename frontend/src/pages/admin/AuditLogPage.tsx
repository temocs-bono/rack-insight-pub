import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ScrollText } from "lucide-react";
import { useState } from "react";
import { Breadcrumb } from "@/components/Breadcrumb";
import { EmptyState } from "@/components/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/services/api";

const PAGE_SIZE = 25;
const ENTITY_TYPES = ["", "cluster", "rack", "device", "credential", "user"];
const ACTIONS = ["", "CREATE", "UPDATE", "DELETE"];

const ACTION_VARIANT: Record<string, "success" | "warning" | "critical"> = {
  CREATE: "success",
  UPDATE: "warning",
  DELETE: "critical",
};

function DiffCell({ raw }: { raw: string | null }) {
  if (!raw) return <span className="text-gray-400">-</span>;
  let pretty = raw;
  try {
    pretty = JSON.stringify(JSON.parse(raw), null, 1);
  } catch {
    // keep raw text
  }
  return (
    <details className="max-w-xs">
      <summary className="cursor-pointer text-xs text-blue-600">view</summary>
      <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-2 text-[11px] text-gray-600">
        {pretty}
      </pre>
    </details>
  );
}

export function AuditLogPage() {
  const [entityType, setEntityType] = useState("");
  const [action, setAction] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["audit", entityType, action, page],
    queryFn: () =>
      api.auditLogs({
        entity_type: entityType || undefined,
        action: action || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="flex flex-col gap-4">
      <Breadcrumb crumbs={[{ label: "Administration" }, { label: "Audit Log" }]} />

      <div className="flex items-end gap-3">
        <Field label="Entity">
          <Select
            className="w-40"
            value={entityType}
            onChange={(e) => {
              setEntityType(e.target.value);
              setPage(1);
            }}
          >
            {ENTITY_TYPES.map((value) => (
              <option key={value} value={value}>
                {value || "All entities"}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Action">
          <Select
            className="w-40"
            value={action}
            onChange={(e) => {
              setAction(e.target.value);
              setPage(1);
            }}
          >
            {ACTIONS.map((value) => (
              <option key={value} value={value}>
                {value || "All actions"}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          Icon={ScrollText}
          title="No audit entries"
          description="Administrative create/update/delete actions will appear here."
        />
      ) : (
        <>
          <Table>
            <THead>
              <TR>
                <TH>When</TH>
                <TH>Who</TH>
                <TH>Action</TH>
                <TH>Entity</TH>
                <TH>Name</TH>
                <TH>Old Value</TH>
                <TH>New Value</TH>
              </TR>
            </THead>
            <TBody>
              {data.items.map((entry) => (
                <TR key={entry.id}>
                  <TD className="whitespace-nowrap text-xs text-gray-500">
                    {new Date(entry.created_at).toLocaleString()}
                  </TD>
                  <TD className="font-medium">{entry.username}</TD>
                  <TD>
                    <Badge variant={ACTION_VARIANT[entry.action] ?? "muted"}>
                      {entry.action}
                    </Badge>
                  </TD>
                  <TD className="uppercase text-xs text-gray-500">{entry.entity_type}</TD>
                  <TD>{entry.entity_name ?? "-"}</TD>
                  <TD>
                    <DiffCell raw={entry.old_value} />
                  </TD>
                  <TD>
                    <DiffCell raw={entry.new_value} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>
              {data.total} entries · page {data.page} of {totalPages}
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
