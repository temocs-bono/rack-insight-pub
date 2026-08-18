import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { KeyboardMusic, Network, Pencil, Plug, Server as ServerIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Breadcrumb } from "@/components/Breadcrumb";
import { ExportMenu } from "@/components/ExportMenu";
import { StatusBadge } from "@/components/StatusBadge";
import { useCluster, useRackLayout } from "@/hooks/queries";
import { api, ApiError } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
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
  const occupied = new Map<number, RackUnit>();
  const covered = new Set<number>();
  for (const unit of units) {
    occupied.set(unit.u_position, unit);
    for (let u = unit.u_position; u < unit.u_position + unit.height; u += 1) {
      covered.add(u);
    }
  }
  const slots: Slot[] = [];
  for (let u = rackHeight; u >= 1; u -= 1) {
    const unit = occupied.get(u);
    if (unit) {
      slots.push({ uPosition: u, height: unit.height, unit });
    } else if (!covered.has(u)) {
      slots.push({ uPosition: u, height: 1, unit: null });
    }
    // covered-but-not-anchor positions are skipped (they belong to a taller device)
  }
  return slots;
}

export function RackDetailPage() {
  const { rackId = "" } = useParams();
  const { data: layout, isLoading } = useRackLayout(rackId);
  const { data: cluster } = useCluster(layout?.rack.cluster_id ?? "");
  const { user } = useAuthStore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [dragOverU, setDragOverU] = useState<number | null>(null);
  const isAdmin = user?.role === "ADMIN";

  const moveDevice = useMutation({
    mutationFn: ({ deviceId, uPosition }: { deviceId: string; uPosition: number }) =>
      api.moveDevice(deviceId, { u_position: uPosition }),
    onSuccess: () => {
      toast.success("Device moved");
      void queryClient.invalidateQueries({ queryKey: ["rack", rackId, "layout"] });
    },
    onError: (err) =>
      toast.error(
        "Move failed",
        err instanceof ApiError ? err.message : "Unexpected error",
      ),
  });

  const slots = useMemo(
    () => (layout ? buildSlots(layout.rack.height, layout.units) : []),
    [layout],
  );

  if (isLoading || !layout) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-6 w-96" />
        <Skeleton className="h-[70vh] w-full max-w-2xl" />
      </div>
    );
  }

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
            { label: layout.rack.name },
          ]}
        />
        <div className="flex items-center gap-3">
          {isAdmin && (
            <span className="text-xs text-gray-400">
              Tip: drag a device onto an empty U to move it
            </span>
          )}
          <ExportMenu scope="rack" targetId={rackId} />
          {isAdmin && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate(`/racks/${rackId}/edit`)}
            >
              <Pencil className="h-4 w-4" /> Edit Layout
            </Button>
          )}
        </div>
      </div>

      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.2 }}
        className="mx-auto flex w-full max-w-3xl flex-col rounded-lg border-4 border-gray-700 bg-gray-800 p-2"
        style={{ height: "calc(100vh - 180px)" }}
      >
        {slots.map((slot) => {
          const heightPercent = (slot.height / layout.rack.height) * 100;
          if (!slot.unit || !slot.unit.device) {
            return (
              <div
                key={slot.uPosition}
                style={{ height: `${heightPercent}%` }}
                className={`flex items-center border-b border-gray-700 px-2 ${
                  dragOverU === slot.uPosition ? "bg-blue-900/60" : ""
                }`}
                onDragOver={
                  isAdmin
                    ? (event) => {
                        event.preventDefault();
                        setDragOverU(slot.uPosition);
                      }
                    : undefined
                }
                onDragLeave={isAdmin ? () => setDragOverU(null) : undefined}
                onDrop={
                  isAdmin
                    ? (event) => {
                        event.preventDefault();
                        setDragOverU(null);
                        const deviceId = event.dataTransfer.getData("text/plain");
                        if (deviceId) {
                          moveDevice.mutate({ deviceId, uPosition: slot.uPosition });
                        }
                      }
                    : undefined
                }
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
              className="group relative flex border-b border-gray-700 px-2 py-0.5"
            >
              <span className="w-8 self-center text-right text-[10px] text-gray-500">
                {slot.uPosition}
              </span>
              <button
                type="button"
                draggable={isAdmin}
                onDragStart={
                  isAdmin
                    ? (event) => event.dataTransfer.setData("text/plain", device.id)
                    : undefined
                }
                onClick={() => navigate(`/devices/${device.id}`)}
                className={`ml-2 flex flex-1 items-center gap-2 rounded border-l-4 px-3 text-left text-sm font-medium transition-transform hover:scale-[1.01] ${statusColor[device.status]} ${isAdmin ? "cursor-grab active:cursor-grabbing" : ""}`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="truncate">{device.display_name ?? device.hostname}</span>
                <span className="ml-auto hidden text-xs opacity-70 lg:inline">
                  {device.model ?? device.device_type}
                </span>
              </button>
              <div className="pointer-events-none absolute left-full top-1/2 z-30 ml-2 hidden w-72 -translate-y-1/2 rounded-md border border-gray-200 bg-white p-3 text-xs shadow-lg group-hover:block">
                <div className="mb-1 flex items-center justify-between">
                  <span className="font-semibold text-gray-900">{device.hostname}</span>
                  <StatusBadge status={device.status} />
                </div>
                <dl className="grid grid-cols-2 gap-x-2 gap-y-1 text-gray-600">
                  <dt>Model</dt>
                  <dd>{device.model ?? "-"}</dd>
                  <dt>Management IP</dt>
                  <dd>{device.management_ip ?? "-"}</dd>
                  <dt>iLO IP</dt>
                  <dd>{device.ilo_ip ?? "-"}</dd>
                  <dt>Type</dt>
                  <dd>{device.device_type}</dd>
                </dl>
              </div>
            </div>
          );
        })}
      </motion.div>
    </div>
  );
}
