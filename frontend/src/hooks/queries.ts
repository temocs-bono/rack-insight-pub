import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/services/api";

export function useClusters() {
  return useQuery({ queryKey: ["clusters"], queryFn: api.clusters });
}

export function useDashboardSummary() {
  return useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: api.dashboardSummary,
    refetchInterval: 60_000,
  });
}

export function useDashboardAlerts() {
  return useQuery({
    queryKey: ["dashboard", "alerts"],
    queryFn: api.dashboardAlerts,
    refetchInterval: 30_000,
  });
}

export function useDashboardHealth() {
  return useQuery({
    queryKey: ["dashboard", "health"],
    queryFn: api.dashboardHealth,
    refetchInterval: 60_000,
  });
}

export function useDeviceHealth(deviceId: string) {
  return useQuery({
    queryKey: ["device", deviceId, "health"],
    queryFn: () => api.deviceHealth(deviceId),
    enabled: Boolean(deviceId),
  });
}

export function useDeviceHistory(deviceId: string) {
  return useQuery({
    queryKey: ["device", deviceId, "history"],
    queryFn: () => api.deviceHistory(deviceId),
    enabled: Boolean(deviceId),
  });
}

export function useCluster(clusterId: string) {
  return useQuery({
    queryKey: ["cluster", clusterId],
    queryFn: () => api.cluster(clusterId),
    enabled: Boolean(clusterId),
  });
}

export function useClusterRacks(clusterId: string) {
  return useQuery({
    queryKey: ["cluster", clusterId, "racks"],
    queryFn: () => api.clusterRacks(clusterId),
    enabled: Boolean(clusterId),
  });
}

export function useRackLayout(rackId: string) {
  return useQuery({
    queryKey: ["rack", rackId, "layout"],
    queryFn: () => api.rackLayout(rackId),
    enabled: Boolean(rackId),
  });
}

export function useDevice(deviceId: string) {
  return useQuery({
    queryKey: ["device", deviceId],
    queryFn: () => api.device(deviceId),
    enabled: Boolean(deviceId),
  });
}

export function useDeviceInventory(deviceId: string) {
  return useQuery({
    queryKey: ["device", deviceId, "inventory"],
    queryFn: () => api.deviceInventory(deviceId),
    enabled: Boolean(deviceId),
  });
}

export function useRefreshDevice(deviceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.refreshDevice(deviceId),
    onSuccess: (inventory) => {
      queryClient.setQueryData(["device", deviceId, "inventory"], inventory);
      void queryClient.invalidateQueries({ queryKey: ["device", deviceId] });
    },
  });
}

export function useUsers() {
  return useQuery({ queryKey: ["users"], queryFn: api.users });
}

export function usePermissions() {
  return useQuery({ queryKey: ["permissions"], queryFn: api.permissions });
}

export function useRoles() {
  return useQuery({ queryKey: ["roles"], queryFn: api.roles });
}

export function useRole(roleId: string) {
  return useQuery({
    queryKey: ["role", roleId],
    queryFn: () => api.role(roleId),
    enabled: Boolean(roleId),
  });
}

export function useUserGroups() {
  return useQuery({ queryKey: ["user-groups"], queryFn: api.userGroups });
}

export function usePlugins() {
  return useQuery({
    queryKey: ["plugins"],
    queryFn: api.plugins,
    refetchInterval: 30_000,
  });
}

export function useCredentials() {
  return useQuery({ queryKey: ["credentials"], queryFn: api.credentials });
}

export function useDeviceTemplates() {
  return useQuery({ queryKey: ["device-templates"], queryFn: api.deviceTemplates });
}

export function useCollectorStatus() {
  return useQuery({
    queryKey: ["collector", "status"],
    queryFn: api.collectorStatus,
    refetchInterval: 30_000,
  });
}

export function useDevices(rackId?: string) {
  return useQuery({
    queryKey: ["devices", rackId ?? "all"],
    queryFn: () => api.devices(rackId),
    enabled: rackId === undefined || Boolean(rackId),
  });
}
