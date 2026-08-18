import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Boxes, Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Breadcrumb } from "@/components/Breadcrumb";
import { EmptyState } from "@/components/EmptyState";
import { useCluster, useClusterRacks } from "@/hooks/queries";
import { api, ApiError } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import { toast } from "@/stores/toast";

const DEFAULT_RACK_HEIGHT = 42;

export function RackListPage() {
  const { clusterId = "" } = useParams();
  const { data: cluster } = useCluster(clusterId);
  const { data: racks, isLoading } = useClusterRacks(clusterId);
  const { user } = useAuthStore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({ name: "", location: "", height: DEFAULT_RACK_HEIGHT });

  const createRack = useMutation({
    mutationFn: () =>
      api.createRack({
        cluster_id: clusterId,
        name: form.name,
        location: form.location || null,
        height: form.height,
      }),
    onSuccess: () => {
      toast.success("Rack created", form.name);
      setCreateOpen(false);
      setForm({ name: "", location: "", height: DEFAULT_RACK_HEIGHT });
      void queryClient.invalidateQueries({ queryKey: ["cluster", clusterId, "racks"] });
      void queryClient.invalidateQueries({ queryKey: ["clusters"] });
    },
    onError: (err) =>
      toast.error(
        "Create failed",
        err instanceof ApiError ? err.message : "Unexpected error",
      ),
  });

  const isAdmin = user?.role === "ADMIN";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <Breadcrumb
          crumbs={[
            { label: "Clusters", to: "/" },
            { label: cluster?.name ?? "…" },
          ]}
        />
        {isAdmin && racks && racks.length > 0 && (
          <Button variant="outline" size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> Create Rack
          </Button>
        )}
      </div>
      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      ) : racks?.length === 0 ? (
        <EmptyState
          Icon={Boxes}
          title="No racks in this cluster"
          description={
            isAdmin
              ? "Create a rack, then place servers and switches on its 42U layout."
              : "No racks have been configured in this cluster yet."
          }
          action={
            isAdmin ? (
              <Button onClick={() => setCreateOpen(true)}>
                <Plus className="h-4 w-4" /> Create Rack
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3 xl:grid-cols-4">
          {racks?.map((rack) => (
            <motion.div key={rack.id} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
              <Card
                className="cursor-pointer transition-shadow hover:shadow-md"
                onClick={() => navigate(`/racks/${rack.id}`)}
              >
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Boxes className="h-5 w-5 text-blue-600" />
                    {rack.name}
                  </CardTitle>
                  <p className="text-xs text-gray-500">
                    {rack.location ?? "No location"} · {rack.height}U
                  </p>
                </CardHeader>
                <CardContent className="flex items-center gap-2 text-sm">
                  <span className="text-gray-600">{rack.device_count} devices</span>
                  <span className="ml-auto flex gap-1">
                    <Badge variant="success">{rack.online_count}</Badge>
                    {rack.warning_count > 0 && (
                      <Badge variant="warning">{rack.warning_count}</Badge>
                    )}
                    {rack.offline_count > 0 && (
                      <Badge variant="critical">{rack.offline_count}</Badge>
                    )}
                  </span>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>
      )}

      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Create Rack"
        footer={
          <>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => createRack.mutate()}
              disabled={!form.name || createRack.isPending}
            >
              {createRack.isPending ? "Creating…" : "Create"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <Field label="Rack Name *">
            <Input
              value={form.name}
              autoFocus
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Location">
            <Input
              value={form.location}
              placeholder="e.g. Row A, Position 3"
              onChange={(e) => setForm({ ...form, location: e.target.value })}
            />
          </Field>
          <Field label="Height (U)">
            <Input
              type="number"
              min={1}
              max={60}
              value={form.height}
              onChange={(e) => setForm({ ...form, height: Number(e.target.value) })}
            />
          </Field>
        </div>
      </Dialog>
    </div>
  );
}
