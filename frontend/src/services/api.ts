import { useAuthStore } from "@/stores/auth";
import type {
  Alert,
  AlertPage,
  AlertSettings,
  AuditLogPage,
  DashboardAlerts,
  DashboardHealth,
  DeviceHealth,
  HistoryPage,
  Plugin,
  BulkDeviceResult,
  CleanupResult,
  ClusterSummary,
  DiscoveredDevice,
  DiscoveryScanResult,
  RetentionPolicy,
  TemplateComplianceReport,
  CollectorDeviceStatus,
  DashboardSummary,
  CollectorRun,
  Credential,
  Device,
  DeviceDetail,
  DeviceInventory,
  DeviceSearchPage,
  DeviceTemplate,
  Me,
  Permission,
  PluginUiSession,
  RackLayout,
  RackSummary,
  Role,
  RoleBinding,
  RoleDetail,
  TokenPair,
  User,
  UserGroup,
} from "@/types";

const API_BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function refreshTokens(): Promise<boolean> {
  const { refreshToken, setTokens, logout } = useAuthStore.getState();
  if (!refreshToken) return false;
  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) {
    logout();
    return false;
  }
  const tokens = (await response.json()) as TokenPair;
  setTokens(tokens.access_token, tokens.refresh_token);
  return true;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  const { accessToken } = useAuthStore.getState();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (response.status === 401 && retry && path !== "/auth/login") {
    const refreshed = await refreshTokens();
    if (refreshed) return request<T>(path, options, false);
    throw new ApiError(401, "Session expired");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // keep statusText
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  login: (username: string, password: string) =>
    request<TokenPair>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<Me>("/auth/me"),

  dashboardSummary: () => request<DashboardSummary>("/dashboard/summary"),

  auditLogs: (params: Record<string, string | number | undefined>) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") query.set(key, String(value));
    }
    return request<AuditLogPage>(`/audit?${query.toString()}`);
  },

  clusters: () => request<ClusterSummary[]>("/clusters"),
  createCluster: (payload: Record<string, unknown>) =>
    request<ClusterSummary>("/clusters", { method: "POST", body: JSON.stringify(payload) }),
  updateCluster: (id: string, payload: Record<string, unknown>) =>
    request<ClusterSummary>(`/clusters/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteCluster: (id: string) => request<void>(`/clusters/${id}`, { method: "DELETE" }),
  clusterRacks: (clusterId: string) =>
    request<RackSummary[]>(`/clusters/${clusterId}/racks`),
  cluster: (clusterId: string) =>
    request<ClusterSummary>(`/clusters/${clusterId}`),

  createRack: (payload: Record<string, unknown>) =>
    request<RackSummary>("/racks", { method: "POST", body: JSON.stringify(payload) }),
  updateRack: (id: string, payload: Record<string, unknown>) =>
    request<RackSummary>(`/racks/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  bulkCreateRacks: (payload: {
    cluster_id: string;
    prefix: string;
    count: number;
    height?: number;
    location?: string | null;
  }) =>
    request<{ created: RackSummary[]; skipped: string[] }>("/racks/bulk", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteRack: (id: string) => request<void>(`/racks/${id}`, { method: "DELETE" }),
  rackLayout: (rackId: string) => request<RackLayout>(`/racks/${rackId}/layout`),
  updateRackLayout: (
    rackId: string,
    units: { u_position: number; height: number; device_id: string | null }[],
  ) =>
    request<RackLayout>(`/racks/${rackId}/layout`, {
      method: "PUT",
      body: JSON.stringify({ units }),
    }),

  devices: (rackId?: string) =>
    request<Device[]>(`/devices${rackId ? `?rack_id=${rackId}` : ""}`),
  searchDevices: (params: Record<string, string | number | undefined>) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") query.set(key, String(value));
    }
    return request<DeviceSearchPage>(`/devices/search?${query.toString()}`);
  },
  device: (deviceId: string) => request<DeviceDetail>(`/devices/${deviceId}`),
  createDevice: (payload: Record<string, unknown>) =>
    request<Device>("/devices", { method: "POST", body: JSON.stringify(payload) }),
  updateDevice: (deviceId: string, payload: Record<string, unknown>) =>
    request<Device>(`/devices/${deviceId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteDevice: (deviceId: string) =>
    request<void>(`/devices/${deviceId}`, { method: "DELETE" }),
  bulkCreateDevices: (payload: Record<string, unknown>) =>
    request<BulkDeviceResult>("/devices/bulk", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  unassignDevice: (deviceId: string) =>
    request<void>(`/devices/${deviceId}/position`, { method: "DELETE" }),

  deviceHealth: (deviceId: string) =>
    request<DeviceHealth>(`/devices/${deviceId}/health`),

  // --- Operations & Alert Center (1.3.0) ---
  alerts: (params: Record<string, string | number | undefined>) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") query.set(key, String(value));
    }
    return request<AlertPage>(`/alerts?${query.toString()}`);
  },
  alert: (id: string) => request<Alert>(`/alerts/${id}`),
  resolveAlert: (id: string) =>
    request<Alert>(`/alerts/${id}/resolve`, { method: "PATCH" }),

  history: (params: Record<string, string | number | undefined>) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") query.set(key, String(value));
    }
    return request<HistoryPage>(`/history?${query.toString()}`);
  },
  deviceHistory: (deviceId: string, page = 1, pageSize = 50) =>
    request<HistoryPage>(`/history/device/${deviceId}?page=${page}&page_size=${pageSize}`),

  dashboardAlerts: () => request<DashboardAlerts>("/dashboard/alerts"),
  dashboardHealth: () => request<DashboardHealth>("/dashboard/health"),

  // --- Plugins (Plugin Platform) ---
  plugins: () => request<Plugin[]>("/plugins"),
  plugin: (id: string) => request<Plugin>(`/plugins/${id}`),
  createPlugin: (payload: Record<string, unknown>) =>
    request<Plugin>("/plugins", { method: "POST", body: JSON.stringify(payload) }),
  updatePlugin: (id: string, payload: Record<string, unknown>) =>
    request<Plugin>(`/plugins/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deletePlugin: (id: string) => request<void>(`/plugins/${id}`, { method: "DELETE" }),
  pluginHealthCheck: (id: string) =>
    request<Plugin>(`/plugins/${id}/health-check`, { method: "POST" }),
  // Mints the short-lived HttpOnly cookie the plugin iframe uses to authenticate
  // same-origin (an iframe navigation cannot carry the SPA's Bearer token).
  createPluginUiSession: () =>
    request<PluginUiSession>("/plugins/ui-session", { method: "POST" }),

  alertSettings: () => request<AlertSettings>("/lifecycle/alert-settings"),
  updateAlertSettings: (payload: AlertSettings) =>
    request<AlertSettings>("/lifecycle/alert-settings", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  discoveries: () => request<DiscoveredDevice[]>("/discovery"),
  discoveryScan: (payload: { targets: string[]; community: string; timeout?: number }) =>
    request<DiscoveryScanResult>("/discovery/scan", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  discoveryImport: (payload: Record<string, unknown>) =>
    request<BulkDeviceResult>("/discovery/import", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  ignoreDiscovery: (id: string) =>
    request<void>(`/discovery/${id}`, { method: "DELETE" }),

  retentionPolicies: () => request<RetentionPolicy[]>("/lifecycle/policies"),
  updateRetentionPolicy: (category: string, payload: Record<string, unknown>) =>
    request<RetentionPolicy>(`/lifecycle/policies/${category}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  runCleanup: () => request<CleanupResult>("/lifecycle/cleanup", { method: "POST" }),

  templateCompliance: (templateId: string) =>
    request<TemplateComplianceReport>(`/device-templates/${templateId}/compliance`),

  deviceTemplates: () => request<DeviceTemplate[]>("/device-templates"),
  createDeviceTemplate: (payload: Record<string, unknown>) =>
    request<DeviceTemplate>("/device-templates", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateDeviceTemplate: (id: string, payload: Record<string, unknown>) =>
    request<DeviceTemplate>(`/device-templates/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteDeviceTemplate: (id: string) =>
    request<void>(`/device-templates/${id}`, { method: "DELETE" }),
  deviceInventory: (deviceId: string) =>
    request<DeviceInventory>(`/devices/${deviceId}/inventory`),
  refreshDevice: (deviceId: string) =>
    request<DeviceInventory>(`/devices/${deviceId}/refresh`, { method: "POST" }),
  moveDevice: (deviceId: string, payload: { u_position: number; height?: number }) =>
    request<Device>(`/devices/${deviceId}/position`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  credentials: () => request<Credential[]>("/credentials"),
  createCredential: (payload: Record<string, unknown>) =>
    request<Credential>("/credentials", { method: "POST", body: JSON.stringify(payload) }),
  updateCredential: (id: string, payload: Record<string, unknown>) =>
    request<Credential>(`/credentials/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteCredential: (id: string) =>
    request<void>(`/credentials/${id}`, { method: "DELETE" }),

  collectorStatus: () => request<CollectorDeviceStatus[]>("/collector/status"),
  collectorLogs: (deviceId: string) =>
    request<CollectorRun[]>(`/collector/devices/${deviceId}/logs`),

  downloadExport: async (
    scope: "device" | "rack" | "cluster" | "all",
    format: "json" | "csv" | "xlsx",
    targetId?: string,
  ): Promise<void> => {
    const { accessToken } = useAuthStore.getState();
    const params = new URLSearchParams({ scope, format });
    if (targetId) params.set("target_id", targetId);
    const response = await fetch(`${API_BASE}/export?${params.toString()}`, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    });
    if (!response.ok) throw new ApiError(response.status, "Export failed");
    const disposition = response.headers.get("Content-Disposition") ?? "";
    const match = /filename="([^"]+)"/.exec(disposition);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = match?.[1] ?? `rack-insight-export.${format === "csv" ? "zip" : format}`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  },

  users: () => request<User[]>("/users"),
  createUser: (payload: Record<string, unknown>) =>
    request<User>("/users", { method: "POST", body: JSON.stringify(payload) }),
  updateUser: (userId: string, payload: Record<string, unknown>) =>
    request<User>(`/users/${userId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteUser: (userId: string) => request<void>(`/users/${userId}`, { method: "DELETE" }),

  // --- Access Management (RBAC) ---
  permissions: () => request<Permission[]>("/permissions"),

  roles: () => request<Role[]>("/roles"),
  role: (id: string) => request<RoleDetail>(`/roles/${id}`),
  createRole: (payload: Record<string, unknown>) =>
    request<Role>("/roles", { method: "POST", body: JSON.stringify(payload) }),
  updateRole: (id: string, payload: Record<string, unknown>) =>
    request<Role>(`/roles/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteRole: (id: string) => request<void>(`/roles/${id}`, { method: "DELETE" }),

  userGroups: () => request<UserGroup[]>("/user-groups"),
  createUserGroup: (payload: Record<string, unknown>) =>
    request<UserGroup>("/user-groups", { method: "POST", body: JSON.stringify(payload) }),
  updateUserGroup: (id: string, payload: Record<string, unknown>) =>
    request<UserGroup>(`/user-groups/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteUserGroup: (id: string) =>
    request<void>(`/user-groups/${id}`, { method: "DELETE" }),

  roleBindings: () => request<RoleBinding[]>("/role-bindings"),
  createRoleBinding: (payload: Record<string, unknown>) =>
    request<RoleBinding>("/role-bindings", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteRoleBinding: (id: string) =>
    request<void>(`/role-bindings/${id}`, { method: "DELETE" }),
};
