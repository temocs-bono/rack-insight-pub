import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { RequirePermission } from "@/components/RequirePermission";
import { AppLayout } from "@/layouts/AppLayout";
import { AuditLogPage } from "@/pages/admin/AuditLogPage";
import { ClusterManagementPage } from "@/pages/admin/ClusterManagementPage";
import { CollectorManagementPage } from "@/pages/admin/CollectorManagementPage";
import { CredentialManagementPage } from "@/pages/admin/CredentialManagementPage";
import { DeviceManagementPage } from "@/pages/admin/DeviceManagementPage";
import { DeviceTemplatesPage } from "@/pages/admin/DeviceTemplatesPage";
import { DiscoveryPage } from "@/pages/admin/DiscoveryPage";
import { LifecyclePage } from "@/pages/admin/LifecyclePage";
import { PluginsPage } from "@/pages/admin/PluginsPage";
import { RackEditorPage } from "@/pages/admin/RackEditorPage";
import { RackManagementPage } from "@/pages/admin/RackManagementPage";
import { RoleDetailsPage } from "@/pages/admin/RoleDetailsPage";
import { RolesPage } from "@/pages/admin/RolesPage";
import { UserGroupsPage } from "@/pages/admin/UserGroupsPage";
import { UserManagementPage } from "@/pages/admin/UserManagementPage";
import { AlertsPage } from "@/pages/AlertsPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { HistoryPage } from "@/pages/HistoryPage";
import { DeviceDetailPage } from "@/pages/DeviceDetailPage";
import { LoginPage } from "@/pages/LoginPage";
import { PluginLauncherPage } from "@/pages/PluginLauncherPage";
import { RackDetailPage } from "@/pages/RackDetailPage";
import { RackListPage } from "@/pages/RackListPage";
import { SearchPage } from "@/pages/SearchPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<AppLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route
              path="/alerts"
              element={
                <RequirePermission permission="alert.view">
                  <AlertsPage />
                </RequirePermission>
              }
            />
            <Route
              path="/history"
              element={
                <RequirePermission permission="history.view">
                  <HistoryPage />
                </RequirePermission>
              }
            />
            <Route path="/clusters/:clusterId" element={<RackListPage />} />
            <Route path="/racks/:rackId" element={<RackDetailPage />} />
            <Route
              path="/racks/:rackId/edit"
              element={
                <RequirePermission permission="rack.layout.edit">
                  <RackEditorPage />
                </RequirePermission>
              }
            />
            <Route path="/devices/:deviceId" element={<DeviceDetailPage />} />
            <Route
              path="/plugins"
              element={
                <RequirePermission permission="plugin.view">
                  <PluginLauncherPage />
                </RequirePermission>
              }
            />
            <Route
              path="/plugins/:name"
              element={
                <RequirePermission permission="plugin.view">
                  <PluginLauncherPage />
                </RequirePermission>
              }
            />
            <Route
              path="/admin/clusters"
              element={
                <RequirePermission permission="cluster.view">
                  <ClusterManagementPage />
                </RequirePermission>
              }
            />
            <Route
              path="/admin/racks"
              element={
                <RequirePermission permission="rack.view">
                  <RackManagementPage />
                </RequirePermission>
              }
            />
            <Route
              path="/admin/device-templates"
              element={
                <RequirePermission permission="template.view">
                  <DeviceTemplatesPage />
                </RequirePermission>
              }
            />
            <Route
              path="/admin/devices"
              element={
                <RequirePermission permission="device.view">
                  <DeviceManagementPage />
                </RequirePermission>
              }
            />
            <Route
              path="/admin/credentials"
              element={
                <RequirePermission permission="credential.view">
                  <CredentialManagementPage />
                </RequirePermission>
              }
            />
            <Route
              path="/admin/plugins"
              element={
                <RequirePermission permission="plugin.view">
                  <PluginsPage />
                </RequirePermission>
              }
            />
            <Route
              path="/admin/collectors"
              element={
                <RequirePermission permission="collector.view">
                  <CollectorManagementPage />
                </RequirePermission>
              }
            />
            <Route
              path="/admin/discovery"
              element={
                <RequirePermission permission="discovery.view">
                  <DiscoveryPage />
                </RequirePermission>
              }
            />
            <Route
              path="/admin/lifecycle"
              element={
                <RequirePermission permission="lifecycle.view">
                  <LifecyclePage />
                </RequirePermission>
              }
            />
            <Route
              path="/admin/audit"
              element={
                <RequirePermission permission="audit.view">
                  <AuditLogPage />
                </RequirePermission>
              }
            />
            <Route
              path="/admin/users"
              element={
                <RequirePermission permission="user.view">
                  <UserManagementPage />
                </RequirePermission>
              }
            />
            <Route
              path="/admin/user-groups"
              element={
                <RequirePermission permission="group.view">
                  <UserGroupsPage />
                </RequirePermission>
              }
            />
            <Route
              path="/admin/roles"
              element={
                <RequirePermission permission="role.view">
                  <RolesPage />
                </RequirePermission>
              }
            />
            <Route
              path="/admin/roles/:roleId"
              element={
                <RequirePermission permission="role.view">
                  <RoleDetailsPage />
                </RequirePermission>
              }
            />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
