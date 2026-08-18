import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  KeyboardMusic,
  LogOut,
  Network,
  Plug,
  Server as ServerIcon,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Breadcrumb } from "@/components/Breadcrumb";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCluster, useDevices, useRackLayout } from "@/hooks/queries";
import { api, ApiError } from "@/services/api";
import { toast } from "@/stores/toast";
import type { DeviceStatus, DeviceType, RackUnit } from "@/types";

const statusColor: Record<DeviceStatus, string> = {
  ONLINE: "bg-green-100 border-green-500 text-green-900",
  WARNING: "bg-orange-100 border-orange-500 text-orange-900",
  OFFLINE: "bg-red-100 border-red-500 text-red-900",
  UNKNOWN: "bg-gray-100 border-gray-400 text-gray-700",
};

const typeIcon: Record<DeviceType, typeof ServerIcon> = {
  SERVER: ServerIcon,
  SWITCH: Network,
  PDU: Plug,
  KVM: KeyboardMusic,
  OTHER: ServerIcon,
};

interface Slot {
  uPosition: number;
  height: number;
  unit: RackUnit | null;
}

function buildSlots(rackHeight: number, units: RackUnit[]): Slot[] {
  const anchors = new Map<number, RackUnit>();
  const covered = new Set<number>();
  for (const unit of units) {
    anchors.set(unit.u_position, unit);
    for (let u = unit.u_position; u < unit.u_position + unit.height; u += 1) {
      covered.add(u);
    }
  }
  const slots: Slot[] = [];
  for (let u = rackHeight; u >= 1; u -= 1) {
    const unit = anchors.get(u);
    if (unit) slots.push({ uPosition: u, height: unit.height, unit });
    else if (!covered.has(u)) slots.push({ uPosition: u, height: 1, unit: null });
  }
  return slots;
}

/**
 * Drag-and-drop 42U rack editor (P4). Devices are moved directly by dragging
 * their block onto an empty U — no automatic shifting of other devices — the
 * same interaction as Rack View. Unplaced devices sit in a side palette and
 * can be dragged into the rack (assign) or removed from it (unassign).
 */
export function RackEditorPage() {
  const { rackId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: layout, isLoading } = useRackLayout(rackId);
  const { data: cluster } = useCluster(layout?.rack.cluster_id ?? "");
  const { data: devices } = useDevices(rackId || undefined);
  const [dragOverU, setDragOverU] = useState<number | null>(null);
  const [paletteHover, setPaletteHover] = useState(false);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["rack", rackId, "layout"] });
    void queryClient.invalidateQueries({ queryKey: ["devices", rackId] });
  };

  const move = useMutation({
    mutationFn: ({ deviceId, u }: { deviceId: string; u: number }) =>
      api.moveDevice(deviceId, { u_position: u }),
    onSuccess: refresh,
    onError: (err) =>
      toast.error("Move failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const unassign = useMutation({
    mutationFn: (deviceId: string) => api.unassignDevice(deviceId),
    onSuccess: () => {
      toast.success("Removed from rack");
      refresh();
    },
    onError: (err) =>
      toast.error("Remove failed", err instanceof ApiError ? err.message : "Unexpected error"),
  });

  const slots = useMemo(
    () => (layout ? buildSlots(layout.rack.height, layout.units) : []),
    [layout],
  );

  const placedIds = useMemo(
    () => new Set((layout?.units ?? []).map((u) => u.device?.id).filter(Boolean)),
    [layout],
  );
  const unplaced = (devices ?? []).filter((d) => !placedIds.has(d.id));

  if (isLoading || !layout) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-6 w-96" />
        <Skeleton className="h-[70vh] w-full max-w-2xl" />
      </div>
    );
  }

  const onDropAtU = (event: React.DragEvent, u: number) => {
    event.preventDefault();
    setDragOverU(null);
    const deviceId = event.dataTransfer.getData("text/plain");
    if (deviceId) move.mutate({ deviceId, u });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <Breadcrumb
          crumbs={[
            { label: "Clusters", to: "/" },
            {
              label: cluster?.name ?? "Cluster",
              to: `/clusters/${layout.rack.cluster_id}`,
            },
            { label: layout.rack.name, to: `/racks/${rackId}` },
            { label: "Edit Layout" },
          ]}
        />
        <Button variant="outline" size="sm" onClick={() => navigate(`/racks/${rackId}`)}>
          Done
        </Button>
      </div>

      <p className="text-sm text-gray-500">
        Drag a device onto an empty U to place or move it — other devices are
        never shifted automatically. Drag a device to the “Unplaced” panel to
        remove it from the rack.
      </p>

      <div className="flex gap-4">
        <div
          className="flex w-full max-w-2xl flex-col rounded-lg border-4 border-gray-700 bg-gray-800 p-2"
          style={{ height: "calc(100vh - 220px)" }}
        >
          {slots.map((slot) => {
            const heightPercent = (slot.height / layout.rack.height) * 100;
            if (!slot.unit?.device) {
              return (
                <div
                  key={slot.uPosition}
                  style={{ height: `${heightPercent}%` }}
                  className={`flex items-center border-b border-gray-700 px-2 ${
                    dragOverU === slot.uPosition ? "bg-blue-900/60" : ""
                  }`}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOverU(slot.uPosition);
                  }}
                  onDragLeave={() => setDragOverU(null)}
                  onDrop={(e) => onDropAtU(e, slot.uPosition)}
                >
                  <span className="w-8 text-right text-[10px] text-gray-500">
                    {slot.uPosition}
                  </span>
                </div>
              );
            }
            const device = slot.unit.device;
            const Icon = typeIcon[device.device_type] ?? ServerIcon;
            return (
              <div
                key={slot.uPosition}
                style={{ height: `${heightPercent}%` }}
                className="flex border-b border-gray-700 px-2 py-0.5"
              >
                <span className="w-8 self-center text-right text-[10px] text-gray-500">
                  {slot.uPosition}
                </span>
                <button
                  type="button"
                  draggable
                  onDragStart={(e) => e.dataTransfer.setData("text/plain", device.id)}
                  onClick={() => navigate(`/devices/${device.id}`)}
                  className={`ml-2 flex flex-1 cursor-grab items-center gap-2 rounded border-l-4 px-3 text-left text-sm font-medium active:cursor-grabbing ${statusColor[device.status]}`}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="truncate">
                    {device.display_name ?? device.hostname}
                  </span>
                  <span className="ml-auto hidden text-xs opacity-70 lg:inline">
                    {device.model ?? device.device_type}
                  </span>
                </button>
              </div>
            );
          })}
        </div>

        <Card
          className={`w-72 shrink-0 ${paletteHover ? "ring-2 ring-orange-400" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setPaletteHover(true);
          }}
          onDragLeave={() => setPaletteHover(false)}
          onDrop={(e) => {
            e.preventDefault();
            setPaletteHover(false);
            const deviceId = e.dataTransfer.getData("text/plain");
            if (deviceId && placedIds.has(deviceId)) unassign.mutate(deviceId);
          }}
        >
          <CardHeader>
            <CardTitle className="text-sm">Unplaced devices</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {unplaced.length === 0 ? (
              <EmptyState
                Icon={LogOut}
                title="All devices placed"
                description="Drag a device here to remove it from the rack."
              />
            ) : (
              unplaced.map((device) => (
                <div
                  key={device.id}
                  draggable
                  onDragStart={(e) => e.dataTransfer.setData("text/plain", device.id)}
                  className="flex cursor-grab items-center gap-2 rounded border border-gray-200 bg-white px-2 py-1.5 text-sm active:cursor-grabbing"
                >
                  <ServerIcon className="h-4 w-4 text-gray-400" />
                  <span className="truncate">{device.hostname}</span>
                  <span className="ml-auto">
                    <StatusBadge status={device.status} />
                  </span>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
