export type UserRole = "ADMIN" | "USER";
export type UserStatus = "ACTIVE" | "DISABLED";
export type DeviceType = "SERVER" | "SWITCH" | "PDU" | "KVM" | "OTHER";
export type DeviceStatus = "ONLINE" | "OFFLINE" | "WARNING" | "UNKNOWN";

export interface MenuPermission {
  key: string;
  permission: string;
}

export interface Me {
  id: string;
  username: string;
  role: UserRole;
  display_name: string | null;
  email: string | null;
  last_login: string | null;
  permissions: string[];
  menus: MenuPermission[];
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface User {
  id: string;
  username: string;
  role: UserRole;
  display_name: string | null;
  email: string | null;
  status: UserStatus;
  enabled: boolean;
  last_login: string | null;
  group_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface Permission {
  id: string;
  code: string;
  name: string;
  category: string;
  description: string | null;
}

export interface Role {
  id: string;
  name: string;
  description: string | null;
  is_system: boolean;
  permission_codes: string[];
  created_at: string;
  updated_at: string;
}

export interface UserGroup {
  id: string;
  name: string;
  description: string | null;
  is_system: boolean;
  member_ids: string[];
  member_count: number;
  role_ids: string[];
  role_names: string[];
  created_at: string;
  updated_at: string;
}

export interface RoleGroupRef {
  id: string;
  name: string;
}

export interface RoleDetail extends Role {
  user_groups: RoleGroupRef[];
  effective_user_count: number;
}

export interface RoleBinding {
  id: string;
  user_group_id: string;
  user_group_name: string;
  role_id: string;
  role_name: string;
  scope_type: string;
  scope_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ClusterSummary {
  id: string;
  name: string;
  vendor: string | null;
  site: string | null;
  description: string | null;
  rack_count: number;
  device_count: number;
  server_count: number;
  switch_count: number;
  online_count: number;
  warning_count: number;
  last_refresh: string | null;
}

export interface RackSummary {
  id: string;
  cluster_id: string;
  name: string;
  location: string | null;
  height: number;
  description: string | null;
  device_count: number;
  online_count: number;
  offline_count: number;
  warning_count: number;
}

export type DeviceOrientation = "FRONT" | "REAR";
export type CredentialType = "REDFISH" | "SSH" | "SNMP";

export interface DeviceTemplate {
  id: string;
  name: string;
  vendor: string | null;
  model: string | null;
  cpu: string | null;
  memory: string | null;
  storage: string | null;
  firmware: string | null;
  nic: string | null;
  description: string | null;
  instance_count: number;
  created_at: string;
  updated_at: string;
}

export interface BulkDeviceResult {
  created: Device[];
  skipped: string[];
  errors: { hostname: string; error: string }[];
}

export interface Device {
  id: string;
  rack_id: string;
  hostname: string;
  display_name: string | null;
  device_type: DeviceType;
  vendor: string | null;
  model: string | null;
  management_ip: string | null;
  ilo_ip: string | null;
  ilo_username: string | null;
  ssh_username: string | null;
  status: DeviceStatus;
  enabled: boolean;
  orientation: DeviceOrientation;
  collector_types: string | null;
  redfish_credential_id: string | null;
  ssh_credential_id: string | null;
  snmp_credential_id: string | null;
  template_id: string | null;
  asset_tag?: string | null;
  serial_override?: string | null;
  description?: string | null;
}

export interface Credential {
  id: string;
  name: string;
  credential_type: CredentialType;
  username: string | null;
  description: string | null;
  has_password: boolean;
  created_at: string;
  updated_at: string;
}

export interface CollectorRun {
  id: string;
  success: boolean;
  duration_ms: number;
  message: string | null;
  trigger: string | null;
  error_code: string | null;
  readable_message: string | null;
  created_at: string;
}

export interface DeviceSearchResult extends Device {
  rack_name: string | null;
  cluster_name: string | null;
  cluster_id: string | null;
}

export interface DeviceSearchPage {
  items: DeviceSearchResult[];
  total: number;
  page: number;
  page_size: number;
}

export type DiscoveryStatus = "PENDING" | "IMPORTED" | "IGNORED";

export interface DiscoveredDevice {
  id: string;
  ip_address: string;
  sysname: string | null;
  sysdescr: string | null;
  sysobjectid: string | null;
  vendor: string | null;
  device_type_guess: string | null;
  serial: string | null;
  status: DiscoveryStatus;
  imported_device_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface DiscoveryScanResult {
  scanned: number;
  reachable: number;
  discovered: DiscoveredDevice[];
}

export interface DeviceComponentStatus {
  device_id: string;
  hostname: string;
  version: string | null;
  compliant: boolean;
}

export interface ComponentCompliance {
  component: string;
  expected_version: string | null;
  compliant: boolean;
  devices: DeviceComponentStatus[];
}

export interface TemplateComplianceReport {
  template_id: string;
  device_count: number;
  compliant: boolean;
  components: ComponentCompliance[];
}

export interface RetentionPolicy {
  id: string;
  category: string;
  retention_days: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CleanupResult {
  deleted: Record<string, number>;
  total: number;
}

export interface AuditLogEntry {
  id: string;
  username: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  entity_name: string | null;
  old_value: string | null;
  new_value: string | null;
  created_at: string;
}

export interface AuditLogPage {
  items: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
}

export interface DashboardSummary {
  total_devices: number;
  online: number;
  warning: number;
  critical: number;
  offline: number;
  unknown: number;
}

// --- Operations & Alert Center (1.3.0) ---
export type AlertSeverity = "INFO" | "WARNING" | "CRITICAL";
export type AlertStatus = "ACTIVE" | "RESOLVED";
export type HealthLabel = "Healthy" | "Warning" | "Critical" | "Unknown";

export interface ChangeItem {
  section: string;
  identifier: string;
  change: "added" | "removed" | "changed";
  field: string | null;
  old: string | null;
  new: string | null;
}

export interface Alert {
  id: string;
  device_id: string;
  hostname: string;
  display_name: string | null;
  vendor: string | null;
  model: string | null;
  rack_id: string | null;
  rack_name: string | null;
  cluster_id: string | null;
  cluster_name: string | null;
  event_type: string;
  category: string;
  severity: AlertSeverity;
  status: AlertStatus;
  subject: string | null;
  message: string;
  changes: ChangeItem[];
  details: Record<string, unknown> | null;
  auto_resolve: boolean;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
}

export interface AlertPage {
  items: Alert[];
  total: number;
  page: number;
  page_size: number;
}

export interface HistoryEntry {
  id: string;
  device_id: string;
  hostname: string | null;
  kind: string;
  title: string;
  changes: ChangeItem[];
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface HistoryPage {
  items: HistoryEntry[];
  total: number;
  page: number;
  page_size: number;
}

export interface DashboardAlerts {
  active_critical: number;
  active_warning: number;
  active_info: number;
  offline_devices: number;
  healthy_devices: number;
  latest_alerts: Alert[];
  critical_devices: Alert[];
  recent_hardware_changes: HistoryEntry[];
  recent_firmware_changes: HistoryEntry[];
}

export interface DashboardHealth {
  healthy: number;
  warning: number;
  critical: number;
  unknown: number;
  offline: number;
  total: number;
}

export interface SensorGroupSummary {
  group: string;
  total: number;
  ok: number;
  breached: number;
  label: HealthLabel;
}

export interface HealthTimelinePoint {
  collected_at: string;
  score: number;
  label: string;
}

export interface DeviceHealth {
  overall_label: HealthLabel;
  overall_score: number | null;
  status: string;
  last_collected_at: string | null;
  sensor_groups: SensorGroupSummary[];
  storage_label: HealthLabel;
  memory_label: HealthLabel;
  network_label: HealthLabel;
  timeline: HealthTimelinePoint[];
}

export interface AlertSettings {
  consecutive_failures_threshold: number;
}

// --- Plugins (Plugin Platform) ---
export type PluginStatus = "HEALTHY" | "UNHEALTHY" | "UNKNOWN" | "DISABLED";

export interface PluginUi {
  type: string;
  path: string;
  title: string | null;
}

export interface Plugin {
  id: string;
  name: string;
  display_name: string;
  description: string | null;
  version: string | null;
  api_version: string;
  endpoint: string;
  enabled: boolean;
  managed_by_config: boolean;
  status: PluginStatus;
  last_health_check: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  failure_reason: string | null;
  ui: PluginUi | null;
  created_at: string;
  updated_at: string;
}

export interface PluginUiSession {
  expires_in: number;
}

export interface CollectorDeviceStatus {
  device_id: string;
  hostname: string;
  display_name: string | null;
  device_type: DeviceType;
  status: DeviceStatus;
  rack_name: string | null;
  cluster_name: string | null;
  last_snapshot_at: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error: string | null;
  last_error_code: string | null;
  last_error_readable: string | null;
  health_score: number | null;
  health_label: string | null;
}

export interface DeviceDetail extends Device {
  health_score: number | null;
  health_label: string | null;
  last_refresh: string | null;
  serial: string | null;
}

export interface LayoutDevice {
  id: string;
  hostname: string;
  display_name: string | null;
  device_type: DeviceType;
  vendor: string | null;
  model: string | null;
  management_ip: string | null;
  ilo_ip: string | null;
  status: DeviceStatus;
}

export interface RackUnit {
  id: string;
  u_position: number;
  height: number;
  device: LayoutDevice | null;
}

export interface RackLayout {
  rack: {
    id: string;
    cluster_id: string;
    name: string;
    location: string | null;
    height: number;
    description: string | null;
  };
  units: RackUnit[];
}

export interface CPU {
  id: string;
  socket: string | null;
  vendor: string | null;
  model: string | null;
  cores: number | null;
  threads: number | null;
  frequency: string | null;
  cache: string | null;
  microcode: string | null;
  serial: string | null;
}

export interface MemoryDimm {
  id: string;
  slot: string | null;
  vendor: string | null;
  part_number: string | null;
  serial: string | null;
  capacity_gb: number | null;
  speed: string | null;
  type: string | null;
  ecc: boolean | null;
  status: string | null;
}

export interface NIC {
  id: string;
  name: string | null;
  vendor: string | null;
  model: string | null;
  mac: string | null;
  firmware: string | null;
  driver: string | null;
  speed: string | null;
  pci_slot: string | null;
  serial: string | null;
  link_status: string | null;
}

export interface Firmware {
  id: string;
  component: string | null;
  version: string | null;
  release_date: string | null;
  health: string | null;
}

export interface Disk {
  id: string;
  slot: string | null;
  vendor: string | null;
  model: string | null;
  serial: string | null;
  capacity: string | null;
  firmware: string | null;
  health: string | null;
}

export interface Storage {
  id: string;
  controller: string | null;
  raid_level: string | null;
  vendor: string | null;
  model: string | null;
  serial: string | null;
  capacity: string | null;
  firmware: string | null;
  health: string | null;
  disks: Disk[];
}

export interface NetworkInterface {
  id: string;
  interface: string | null;
  ipv4: string | null;
  ipv6: string | null;
  gateway: string | null;
  dns: string | null;
  vlan: string | null;
  bond: string | null;
  mtu: number | null;
  speed: string | null;
  duplex: string | null;
  mac: string | null;
}

export interface VM {
  id: string;
  name: string | null;
  uuid: string | null;
  state: string | null;
  vcpu: number | null;
  memory: string | null;
  os: string | null;
  kernel: string | null;
  ip: string | null;
}

export interface Sensor {
  id: string;
  type: string | null;
  name: string | null;
  value: string | null;
  unit: string | null;
  status: string | null;
  upper_threshold: string | null;
  lower_threshold: string | null;
}

export interface SwitchInventory {
  id: string;
  model: string | null;
  ios_version: string | null;
  serial: string | null;
  uptime: string | null;
}

export interface SnapshotMeta {
  id: string;
  collected_at: string;
  collector_version: string;
  redfish_success: boolean;
  ssh_success: boolean;
  virsh_success: boolean;
  duration_ms: number;
}

export interface DeviceInventory {
  snapshot: SnapshotMeta | null;
  cpus: CPU[];
  memories: MemoryDimm[];
  nics: NIC[];
  firmwares: Firmware[];
  storages: Storage[];
  networks: NetworkInterface[];
  vms: VM[];
  sensors: Sensor[];
  switch: SwitchInventory | null;
}
