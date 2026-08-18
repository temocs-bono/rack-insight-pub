# Release Notes

## 1.5.0 — Plugin Platform (Backend + Frontend)

Extends the backend-only plugin system into a full **Backend + Frontend Plugin
Platform**. A plugin can now ship its own **frontend**, embedded by the Core as a
same-origin **iframe**, alongside its backend API — still as an independent
container, still added **without modifying Core**. Fully backward compatible: a
plugin with no `ui` in its manifest behaves exactly as before.

### What changed

- **Manifest UI descriptor** — `ui: { type: "iframe", path, title }`. Parsed and
  surfaced on `PluginResponse.ui`; absent ⇒ backend-only.
- **Core UI proxy** — `GET /api/plugins/{name}/ui/{path}` serves the plugin's own
  frontend same-origin (with `Content-Security-Policy: frame-ancestors 'self'`),
  so the browser never learns the plugin's Service DNS name. The existing API
  proxy (`…/proxy/…`) is unchanged.
- **Plugin-UI cookie** — `POST /api/plugins/ui-session` mints a short-lived,
  HttpOnly, `SameSite=Strict`, `Path=/api/plugins` cookie so an iframe (which
  cannot carry a Bearer header) authenticates same-origin. Both proxies accept
  cookie **or** Bearer (`get_current_user_flexible`); RBAC is unchanged.
- **Inventory for plugins** — `GET /api/plugins/inventory/servers` exposes a
  read-only, credential-free view of the Core inventory, so a plugin never
  replicates devices in its own DB.
- **Long-running Job Contract** — documented and demonstrated: `POST /api/jobs`,
  `GET /api/jobs/{id}`, `GET /api/jobs/{id}/results`, cancel; states
  `queued → running → completed | failed | cancelled`.
- **Reference plugin** — `plugins/example-plugin` is now a full template: backend
  API, in-memory jobs, and a self-contained `/ui/` frontend that lists Core
  inventory and runs jobs through the Core proxy.
- **Core frontend** — a top-level **Plugins** launcher (list + health + embedded
  iframe); **Administration → Plugins** kept as **Plugin Registry**.
- **Docs** — the Plugin Developer Guide is rewritten as a 25-section platform
  guide (UI proxy, iframe auth, inventory, jobs, security, and a safe
  "Server Script Runner" case study). No SSH capability is shipped.

### Compatibility

Backward compatible. No existing API was renamed or removed; DB schema, Auth,
RBAC, and Inventory are reused as-is. No Module Federation, extra microservices,
message brokers, or per-plugin inventory DBs were introduced.

## Unreleased — Kubernetes / ArgoCD Deployment Architecture

A **deployment-architecture migration**: the official testbed/production runtime
moves from Docker Compose to **Kubernetes + ArgoCD (GitOps)**. This is
infrastructure only — **no application logic, API, DB schema, RBAC, alert,
collector, inventory or plugin-contract change**, so the app version is not
bumped and all existing functionality is preserved.

### What changed

- **Kustomize** manifests under `deploy/kubernetes/` (`base` + `overlays/testbed`)
  for every component: frontend, backend, PostgreSQL (StatefulSet + PVC), Redis,
  example-plugin, plus an **Ingress** that replaces the Docker-Compose nginx
  reverse proxy (`/api`,`/docs`,`/openapi.json` → backend; `/` → frontend).
- **ArgoCD Application** tracking **`main` only** (`deploy/argocd/application.yaml`);
  feature branches are CI-tested but never auto-deployed.
- **CI/CD** (`.github/workflows/ci.yml`): PR → build+test; main → build & push
  **immutable commit-SHA-tagged** images, then a GitOps commit bumps the overlay
  tags so ArgoCD rolls the cluster forward. `:latest` is never used.
- **Docker Compose** is retained strictly for **local development**; Kubernetes
  is the official deployment path.
- Health probes use the app's real endpoints (`/api/health`, `/`, `/healthz`,
  `/readyz`, `pg_isready`, `redis-cli ping`). Service-to-service traffic uses
  Kubernetes Service DNS; because those names match the app's existing env
  defaults (`postgres`, `redis`), **no application code changed**.
- New guide `docs/deployment.md` (config reference, immutable image
  flow, air-gap, troubleshooting); README rewritten around the new model; the
  plugin guide gained the end-to-end GitOps plugin lifecycle.

### Why Kustomize (not Helm)

Built into `kubectl` and natively supported by ArgoCD — no extra binary or chart
repository, which suits **air-gapped** clusters. `base` + `overlays` give clean
per-environment separation (testbed / production / air-gapped).

### Compatibility

Fully backward compatible. The same container images run under both Docker
Compose (local) and Kubernetes (testbed/production). Migrations still apply
automatically on backend startup.

## 1.4.0 (2026-07-10) — Plugin Architecture Foundation

Establishes the official **Plugin Extension Point**: a new team member can build
a feature as an independent backend container and register it with Rack Insight
**without modifying Core**. This is a *foundation* — Registry + Contract + Health
+ Proxy + Example Plugin + Frontend discovery — not an MSA rewrite. All existing
features stay in Core and are unchanged. One additive migration (0012). Designed
for **air-gapped** operation (no external internet/SaaS/service-discovery
dependency).

### Architecture

```
Rack Insight Core (Auth/RBAC, Inventory, Operations, Alert, Audit,
                   Plugin Registry, Plugin Proxy)
        │
   Plugin Contract   (GET /plugin/manifest, /healthz, /readyz)
        │
  Example Plugin • Plugin B • Plugin C   (independent containers)
```

### Backend
- **Contract** — a plugin serves `GET /plugin/manifest` (name, displayName,
  version, apiVersion, health/ready endpoints). Parsed camelCase or snake_case;
  unknown fields ignored (forward compatible).
- **Registry** — new `plugins` table (migration 0012). Configuration
  (endpoint/enabled) is kept distinct from observed runtime state
  (status/last_health_check/last_success/last_failure/failure_reason).
- **Registration** — config-based and air-gap friendly: `PLUGINS_CONFIG` (inline
  JSON) or `PLUGINS_CONFIG_FILE` (a JSON file / Kubernetes ConfigMap), seeded
  idempotently on every startup. Plugins can also be registered via the API/UI.
- **Health** — a dedicated background monitor probes each plugin on a short
  interval and on demand. `HEALTHY / UNHEALTHY / UNKNOWN / DISABLED`. Every call
  is timeout-bounded and failure-isolated: **a plugin that is down, slow, or
  returns a malformed manifest never affects Core.**
- **Proxy foundation** — `GET|POST /api/plugins/{name}/proxy/{path}`. The Core
  authenticates the user, checks `plugin.proxy`, then forwards. Unknown plugin →
  404; disabled/unreachable → 503 (never a Core 500 or a hang). The Core does
  not forward its JWT to plugins.
- **API** — `GET/POST/PATCH/DELETE /api/plugins`, `GET /api/plugins/{id}`,
  `POST /api/plugins/{id}/health-check`.
- **Security** — new core permissions `plugin.view`, `plugin.manage`,
  `plugin.proxy` seeded into the system roles. Plugin-specific permissions use
  the reserved `plugin.<name>.<action>` namespace. Plugin lifecycle and health
  transitions are written to the audit log.

### Example Plugin
- `plugins/example-plugin/` — a real standalone FastAPI container implementing
  the contract (`/plugin/manifest`, `/healthz`, `/readyz`, `/api/status`,
  `/api/echo`) with its own Dockerfile, requirements and README. Shares no code
  with Core.

### Deployment (air-gapped)
- `example-plugin` added to `docker-compose.yml` (image-based) and
  `docker-compose.build.yml`. Core reaches it at the service DNS
  `http://example-plugin:8080` (identical in compose and Kubernetes) — never
  localhost. The Core does **not** `depends_on` any plugin.
- `deploy/local/plugins.json` — a ConfigMap-style registration file mounted into the
  backend (`PLUGINS_CONFIG_FILE=/config/plugins.json`).
- `deploy/kubernetes/example-plugin.yaml` — Deployment + Service + ConfigMap.
- `deploy/offline/build_and_export.sh` builds and bundles plugin images.

### Frontend
- **Administration → Plugins** — table (Name, Display Name, Version, API
  Version, Status, Endpoint, Last Health Check, Enabled), a detail dialog (with
  last success/failure and failure reason), Register, Enable/Disable, and
  Health-Check actions. Permission-gated (`plugin.view` to see,
  `plugin.manage` to change). The 1.2.2 navigation (Dashboard / Inventory /
  Operations / Administration / Access Management) is preserved; Plugins is
  added under Administration.

### Explicitly out of scope (future releases)
- Dynamic UI (Module Federation, runtime JS bundles, iframe plugin UI, arbitrary
  component injection). This patch delivers frontend **discovery** only.
- Plugin events flowing into the Alert Engine — documented extension point; the
  event model already tolerates `plugin.*` event types (AlertPolicy maps unknown
  types to the `Other` category), so it can be added without a contract change.

### Migration notes (1.3.x → 1.4.0)
- `docker compose up -d` applies migration 0012 automatically. No data backfill.
- No existing table, API, permission, or navigation item changed. Existing
  1.2.2/1.3.x functionality is unaffected.

## 1.3.1 (2026-07-10) — Alert Engine responsibility split

A maintainability patch on the 1.3.0 Alert Engine. The architecture is
unchanged (Collector → Snapshot → Event Engine → Alert Engine → History) and no
behaviour changes; the Alert Engine simply stops owning every responsibility.
One additive migration (0011); fully backward compatible.

### What moved out of the Alert Engine

- **AlertPolicy** (`services/alert_policy.py`) — given an Event, returns the
  alert **category**, **severity**, and **auto-resolve** flag. Pure: no
  database, no alert creation/resolution, no history. Future rules (e.g.
  `FirmwareChanged → WARNING`, `CollectorFailed → CRITICAL after N failures`)
  now have one obvious home in `_resolve_severity` without touching callers.
- **AlertBuilder** (`services/alert_builder.py`) — constructs the `Alert`
  model from `(event, device, policy)` and nothing else. Never resolves,
  deduplicates, writes history, or hits the database. Every alert is built
  ACTIVE; the engine decides whether to immediately resolve it.
- **Subject** now lives on the **Event**. The Event Engine knows what changed
  (sensor name, DIMM slot, firmware component, NIC…) and records
  `Event.subject`; the Alert Engine reuses `event.subject` instead of parsing
  the JSON details.

### Alert Category vs Event Type

`Event.event_type` is *what happened*; `Alert.category` is now the *operational
domain* the UI groups by:

| Event type(s)                                   | Category      |
|-------------------------------------------------|---------------|
| HardwareChanged                                 | Hardware      |
| FirmwareChanged                                 | Firmware      |
| DeviceOffline, DeviceRecovered, NetworkReachabilityChanged | Connectivity |
| CollectorFailed                                 | Collector     |
| CredentialFailed                                | Credential    |
| SensorThresholdExceeded, SensorRecovered        | Health        |

`Alert` now stores **both** `event_type` and `category`. The Alert Center
filters by category (with the event type shown per row); the alerts API keeps
the `category` filter (now the domain) and adds an `event_type` filter. The
alert lifecycle (resolution, dedupe, escalation) keys off `event_type`.

### The slimmed Alert Engine

`process_events` now reads as its responsibilities: persist events → resolve
counterparts (recovery/escalation) → deduplicate active state alerts → ask
AlertPolicy → build with AlertBuilder → persist → record immutable history.

### Migration notes (1.3.0 → 1.3.1)

- Migration 0011 is additive: adds `events.subject` and `alerts.event_type`
  (indexed), and backfills existing alerts (`event_type = category`, then
  reclassifies `category` to the operational domain). `docker compose up -d`
  applies it automatically.
- Behaviour preserved exactly: one event → one alert, recovery events create
  already-resolved INFO alerts, Hardware/Firmware alerts require manual
  resolve, state alerts auto-resolve, active state alerts are deduplicated,
  history is immutable, and all existing endpoints keep working.

## 1.3.0 (2026-07-10) — Operations & Alert Center

A major release: Rack Insight becomes an **Operations Platform**. The primary
screen is no longer inventory management — administrators immediately see
operational issues, hardware changes and server health. Fully backward
compatible with 1.2.x: no existing API changed, one additive migration (0010),
existing inventory tables untouched.

### Architecture

    Collector -> Inventory Snapshot -> Event Engine -> Alert Engine -> Frontend

- **Collector** only collects inventory and saves a snapshot (the existing
  immutable `snapshots` store — one snapshot per successful collection — plus
  its per-section inventory tables is the snapshot store; nothing was
  duplicated). The collector never creates alerts.
- **SnapshotService** (`services/snapshot_service.py`) is the single entry
  point for a collection cycle; both manual refresh and the background
  scheduler run through it.
- **Event Engine** (`services/event_engine.py`) is the only producer of
  Events. It always compares snapshot **N-1 vs N** — never live inventory,
  never the whole history — and detects meaningful changes plus state
  transitions. Event types are extensible strings:
  `HardwareChanged`, `FirmwareChanged`, `DeviceOffline`, `DeviceRecovered`,
  `SensorThresholdExceeded`, `SensorRecovered`, `CollectorFailed`,
  `CredentialFailed`, `NetworkReachabilityChanged`.
- **Alert Engine** (`services/alert_engine.py`) converts Events into Alerts
  (one event -> one alert), deduplicates active state alerts, resolves state
  alerts automatically when the next collection shows normal state, and keeps
  Hardware/Firmware alerts ACTIVE until an administrator resolves them.

### Hardware change policy

Alerts fire only for meaningful inventory changes: CPU replaced, memory
capacity/DIMM changed, disk added/removed, NIC added/removed, management
controller / PSU firmware changed, firmware versions changed. Sensor value
fluctuations (temperature, fan RPM, voltage, power draw) and BIOS settings
never create change alerts — sensors belong to Health only.

### Alerts

- Severity INFO / WARNING / CRITICAL; status ACTIVE / RESOLVED.
- Hardware/Firmware alerts: manual resolve (recorded in history).
  State alerts: auto-resolve on recovery (`resolved_by: system`).
- Offline detection uses a **configurable consecutive-failure threshold**
  (default 3, Lifecycle page). Credential failures alert immediately.
- Recovery events produce an already-RESOLVED INFO alert so the timeline stays
  complete without lingering noise.

### Device History (permanent)

Immutable `device_history` records: firmware upgrades, hardware replacements,
collector failures, recoveries, manual resolves. History is never updated and
never disappears — deletion requires explicitly enabling the (default-off)
`history` retention policy.

### Health model

- New `GET /api/devices/{id}/health`: overall health, sensor groups
  (temperature / power / fan / other), storage / memory / network health
  (Healthy / Warning / Critical / Unknown), and a health timeline across
  recent snapshots.
- Device Detail gains a **Health** tab (sensor cards + timeline); the old
  Sensor tab lives inside it. Sensor breaches only alert after N consecutive
  collections (lifecycle policy).

### Lifecycle policy extensions

- `GET/PATCH /api/lifecycle/alert-settings`: consecutive-failure threshold.
- New retention categories: `resolved_alerts` (only RESOLVED alerts are ever
  pruned) and `history` (ships **disabled = permanent**).

### Alert Center UI

- New top-level **Alerts** sidebar section: **Alerts** and **History** pages.
- Alert table: Severity, Status, Category, Cluster, Rack, Hostname, Message,
  Created, Resolved — with filters (severity, status, cluster, vendor, model,
  hostname, date range, category, search), newest first, pagination. Clicking
  an alert opens Device Detail; a change icon opens the Diff Viewer.
- **Notification bell** in the header (UI only — no email/Slack/Teams/SMS):
  unread count, click opens the Alert Center.
- **Diff Viewer**: visual before -> after for hardware/firmware changes,
  reused across the Alert Center, Dashboard and Device History.

### Dashboard (operations-first)

Top cards: Critical / Warning / Info alerts, Offline devices, Healthy
devices. Latest Alerts, Critical Devices, Recent hardware changes, Recent
firmware changes. Cluster -> Rack -> Device browsing remains unchanged below.

### Device Detail

Tabs are now Overview / **Health** / Hardware / Firmware / Network / Storage /
VM / **History**. Overview adds Last Alert + Last Firmware version. The
**Drift UI is removed** — hardware changes are Alerts, and History stores the
permanent record (the `/api/devices/{id}/drift` endpoint remains for API
compatibility).

### API additions

`GET /api/alerts`, `GET /api/alerts/{id}`, `PATCH /api/alerts/{id}/resolve`,
`GET /api/history`, `GET /api/history/device/{id}`,
`GET /api/dashboard/alerts`, `GET /api/dashboard/health`,
`GET /api/devices/{id}/health`, `GET/PATCH /api/lifecycle/alert-settings`.
New permissions `alert.view`, `alert.resolve`, `history.view` are seeded into
the system roles automatically (Viewer: view-only; Operator: +resolve).

### Performance

The Event Engine compares exactly two consecutive snapshots; history records
are generated once. Indexes on `device_id`, `snapshot_id`, alert `status`,
`severity` and `created_at` (migration 0010).

### Migration notes (1.2.x -> 1.3.0)

- `docker compose up -d` applies migration 0010 automatically at startup.
- The existing `snapshots` + per-section inventory tables serve as the
  inventory snapshot store (`inventory_snapshots`/`inventory_snapshot_items`
  in the spec); no data is duplicated and nothing is renamed.
- The background scheduler now retries **all enabled devices** (previously
  only ONLINE ones) so offline devices can auto-recover and their alerts
  auto-resolve.
- Alerts/history start empty; events are generated from the first collection
  after the upgrade.

## 1.2.2 (2026-07-10) — Administration UX & Navigation

A UX and navigation release that simplifies administration for large
datacenter environments. No backend architecture, authentication or RBAC logic
changes — existing APIs are reused, the `role_bindings` table is preserved, and
everything is backward compatible with 1.2.1. Two small additive API extensions
support the new UI (no migration required).

### Sidebar — grouped, collapsible navigation

- The left navigation is now grouped into **collapsible sections**: Dashboard
  (+ Inventory Search) at the top, then **Inventory** (Clusters, Racks,
  Devices, Device Templates), **Operations** (Discovery, Collector, Lifecycle),
  **Administration** (Credentials), and **Access Management** (Users, User
  Groups, Roles, Audit Log).
- Expanded/collapsed state is **remembered** (persisted in `localStorage`).
- Sections only appear when the user has permission for at least one item, so
  the menu stays compact and permission-driven.
- Administration pages open **directly** from the Inventory section — no
  hierarchical drill-down. The Dashboard keeps its operational
  Cluster → Rack → Device browse flow, unchanged.

### Role Bindings folded into the User Group editor

- The standalone **Role Bindings** page is **removed** from the UI; role
  bindings are no longer exposed as a separate concept. (The `role_bindings`
  table and its `/api/role-bindings` endpoints are unchanged.)
- Editing a **User Group** now manages group info, **members**, and **assigned
  roles** in a single dialog. Saving updates the role_bindings table internally
  via `role_ids` on `POST/PATCH /api/user-groups`. The built-in Administrator
  binding is still protected from removal.

### Role Details page

- Clicking a role opens a dedicated **Role Details** page
  (`GET /api/roles/{id}`) showing name, description, a System Role indicator,
  assigned permissions (grouped), assigned user groups, and the **effective
  user count**. System roles remain read-only; custom roles are editable in
  place.

### Permissions

- The standalone **Permissions** page is **removed** from navigation.
  Permissions now appear only inside the Role editor and Role Details. They
  remain system-managed (the `/api/permissions` catalog endpoint is unchanged).

### Refactoring

- Extracted reusable UI: `CheckboxList`, `PermissionPicker`, and a shared
  `RoleEditorDialog` (used by both role creation and editing) to remove
  duplication across the Access Management pages.

### API additions (additive, no migration)

- `user_groups` create/update accept `role_ids` and the response includes
  `role_ids`; saving syncs the group's GLOBAL role bindings.
- `GET /api/roles/{id}` returns role detail with bound user groups and the
  effective user count.

## 1.2.1 (2026-07-10) — Access Management (RBAC)

Replaces the standalone User Management page with a full Role-Based Access
Control architecture. Authorization now flows:

    User → User Group → Role Binding → Role → Permissions → Visible Menus + Allowed Actions

Users never receive permissions directly — they inherit them through User
Groups, which are granted Roles via Role Bindings, and each Role carries a set
of business-action Permissions. Fully backward compatible: passwords and the
existing JWT login are unchanged, and one additive migration (0009) creates the
RBAC tables and extends `users`. Existing admin accounts are migrated
automatically into a built-in **Administrators** group bound to the
**Administrator** role, so nothing changes for current operators.

### Data model (migration 0009, additive)

- New tables: `permissions`, `roles`, `role_permissions`, `user_groups`,
  `user_group_members`, `role_bindings`.
- `users` extended with `display_name`, `email`, `status` (existing rows get
  `status='ACTIVE'`; `enabled` remains the authoritative login gate).
- `role_bindings.scope_type` defaults to `GLOBAL` and the schema is
  future-compatible with `CLUSTER` / `RACK` scoping (`scope_id`) without a
  further migration.
- Seed data (permission catalog, the Administrator/Operator/Viewer system
  roles, their permission maps, the Administrators group + binding, and the
  admin migration) is applied idempotently at startup — the same pattern used
  for retention policies in 1.2.0 — so new permissions in future releases seed
  automatically.

### Permissions & system roles

- Permissions are **business-action codes** grouped by domain, e.g.
  `dashboard.view`, `cluster.create`, `rack.layout.edit`, `device.install`,
  `collector.run`, `discovery.scan`, `role.update`, `user.create`.
- Three built-in **system roles** (read-only, cannot be edited or deleted):
  **Administrator** (all permissions), **Operator** (inventory, collectors and
  discovery — no access management), **Viewer** (read-only).
- Custom roles can be created with any subset of permissions.

### Centralized authorization

- A single `RequirePermission("<code>")` dependency guards every endpoint —
  no per-controller role checks. Missing permission returns **HTTP 403**.
- Permission resolution walks the User → Group → Binding → Role → Permission
  chain. The legacy `ADMIN` role remains a break-glass superuser so an
  administrator can never be locked out.
- The built-in Administrator binding cannot be removed and system roles/groups
  cannot be deleted (lockout protection). Password hashes are never exposed.

### Access Management API

- `GET /api/permissions` (read-only catalog).
- `GET/POST/PATCH/DELETE /api/roles` (system roles are read-only).
- `GET/POST/PATCH/DELETE /api/user-groups` (with membership management).
- `GET/POST/DELETE /api/role-bindings`.
- `GET/POST/PATCH/DELETE /api/users` extended with display name, email, status
  and group membership.
- `GET /api/auth/me` now returns the user's effective `permissions` and the
  menu→permission map so the frontend stays in sync with the backend.

### Frontend

- New **Access Management** sidebar section: Users, User Groups, Roles, Role
  Bindings, and a read-only Permissions catalog.
- Reusable permission-aware components: `<RequirePermission>` (route guard) and
  `<PermissionGate>` (hides buttons/controls). The sidebar and every admin route
  are now **permission-driven** — users only see what they can access.
- Frontend checks are UX-only; the backend is always authoritative.

## 1.2.0 (2026-07-08) — Operational Automation & Discovery

The first operational-automation milestone. Six additive features turn the
inventory tool into a datacenter management platform. Fully backward
compatible: no breaking API changes, the Device Template / Installed Device
model and the Rack Editor are unchanged, and all 1.1.x features keep working.
One additive migration (0008) adds two new tables.

### F1 — SNMP Discovery

- `POST /api/discovery/scan` walks standard SNMP system OIDs (sysDescr,
  sysObjectID, sysName) across a set of targets (single IPs and/or CIDR blocks,
  up to 1024 hosts) and stores each reachable host as a **PENDING**
  `DiscoveredDevice`. Vendor and device type are inferred from sysDescr.
- Discovery collects identification data only and **never creates Installed
  Devices automatically**. `GET /api/discovery` lists pending discoveries;
  `DELETE /api/discovery/{id}` ignores one.
- SNMP support (pysnmp) is an optional dependency imported lazily: the platform
  runs without it and the scan endpoint returns a clear 503 until it is
  installed (it ships in the backend image).
- New **SNMP Discovery** admin page: scan form, results table, ignore.

### F2 — Discovery Import Wizard

- `POST /api/discovery/import` creates Installed Devices from selected
  discoveries, **reusing the existing bulk device-creation logic** (no
  duplicated hardware or provisioning code). Hostname and management IP are
  pre-filled (IP defaults to the discovered address) and editable before
  confirming; imported discoveries are marked IMPORTED and linked to the new
  device.

### F3 — Initial Collection Workflow

- After onboarding (Discovery import and the Provisioning wizard), an obvious
  **Finish & Collect / Install & Collect** action runs the first inventory
  collection immediately, reusing the existing per-device refresh. Collection
  stays manual — no scheduled collection was added.

### F4 — Inventory Drift Detection

- `GET /api/devices/{id}/drift` compares a device's two most recent
  **successful** snapshots and reports added / removed / changed hardware per
  section — Firmware/BIOS, CPU, Memory, Storage, NIC, Network, and serial
  numbers. A new **Drift** tab on Device Detail shows the differences.

### F5 — Lifecycle Management

- Admin-configurable retention per category (`collector_runs`, `snapshots`,
  `discovery`) via `GET/PATCH /api/lifecycle/policies`, disabled by default.
- `POST /api/lifecycle/cleanup` runs cleanup on demand; enabled policies are
  also applied automatically by the existing background scheduler (no new
  scheduler introduced). **Current inventory is always preserved** — the latest
  snapshot per device is never deleted regardless of age.
- New **Lifecycle & Retention** admin page.

### F6 — Firmware Compliance

- `GET /api/device-templates/{id}/compliance` compares firmware across every
  device using a template, treats the most common version per component as the
  baseline, and flags mismatches. A **Firmware Compliance** dialog on the
  Device Templates page shows per-component, per-device status.

### Schema

- Migration 0008 (additive): `discovered_devices` and `retention_policies`
  tables. No existing table changed. Retention rows are seeded (disabled) on
  startup.

### Upgrade notes

- `docker compose` up/pull the 1.2.0 images. Migration 0008 runs automatically.
- New optional Python dependency `pysnmp` (bundled in the backend image) enables
  SNMP Discovery.
- Default image tag is now `1.2.0`.

## 1.1.3 (2026-07-08)

Final stabilization patch before 1.2.0. Correctness, consistency and
integrity fixes across the rack-placement and provisioning workflows. No
breaking API changes, no model redesign; all existing data remains valid. One
data-safe migration (0007) cleans up records stranded by an older bug.

### Rack placement (Required Fix 1) — bugs fixed

- **Orphan rack placements corrupted the layout.** `rack_units.device_id` is
  `ON DELETE SET NULL`, so deleting an Installed Device left its rack_unit
  behind with a NULL device — permanently occupying its U slot and rendering a
  dead cell that no device could be placed into. `delete_device` now removes
  the placement, and **migration 0007** purges any orphans left by older
  versions. Result: deleting a device frees its U immediately.
- **Overlap check skipped orphan/NULL rows.** `move_device` excluded the
  device's own unit with `RackUnit.device_id != device_id`, which in SQL also
  excludes NULL-device rows — so a stranded slot both blocked moves and could
  raise a 500 on the unique `(rack_id, u_position)` constraint. Overlap now
  excludes the device's own unit by its **unit id**.
- **`create_device` performed no placement validation.** Creating a device at
  an occupied U raised an opaque 500 (unique-constraint violation) and rack
  height was never checked. It now returns a meaningful 422, consistent with
  `move_device` and bulk creation.
- All three placement paths (create / move / bulk) now share one
  `placement_service` (rack-height + overlap), removing duplicated,
  divergent logic.

### Bulk provisioning (Required Fix 2)

- Added **duplicate-IP validation** within a batch (Management IP and iLO IP);
  conflicts are reported and the whole batch rolls back, matching the existing
  duplicate-hostname behavior. The provisioning wizard now also flags duplicate
  hostnames/IPs client-side before submission.

### Data & business-logic integrity (Required Fix 4/5)

- **PATCH could strand placements.** Moving a device to another rack via
  `PATCH /api/devices/{id}` left its rack_unit in the old rack. The update now
  clears the stale placement (device becomes unplaced until re-positioned).
- **Hostname uniqueness is now enforced consistently.** Single-device create
  and update reject a duplicate hostname within the same rack (409) — bulk
  already did this.
- **Template references are validated on update.** `PATCH` with a non-existent
  `template_id` now returns 422 instead of failing at the database.
- Deleting a template in use remains blocked; deleting a rack still cascades to
  its devices and placements (no orphans).

### Frontend / backend consistency (Required Fix 3) & UI polish (Required Fix 6)

- Removed duplicated placement logic; validation errors are now meaningful
  (422 with a clear message) instead of generic 500s.
- Provisioning wizard: client-side duplicate hostname/IP guards with inline
  messages and a disabled Install button until resolved.

### Upgrade notes

- `docker compose` up/pull the 1.1.3 images. Migration 0007 runs automatically
  and is data-safe (removes only NULL-device orphan rack_units).
- Default image tag is now `1.1.3`.

## 1.1.2 (2026-07-08)

Patch release focused on administrator provisioning productivity. No database
changes, no model changes, no breaking API changes — the 1.1.1 Device Template
/ Installed Device model and the drag-and-drop rack editor are untouched.

### Provisioning wizard (P1–P5)

A two-step **"Provision Multiple Devices"** wizard replaces the simple bulk
dialog on the Installed Devices page:

1. **Setup** — pick a Device Template, quantity, hostname prefix, an optional
   **Default Credential**, and choose Manual or Generate-Sequential mode for
   Management IP and iLO IP (with a start address each).
2. **Review** — an editable table (Hostname, Management IP, iLO IP, Credential,
   Rack Position U) pre-filled with generated values. **Every cell is
   editable**; rows can be removed. Confirm installs all rows in one request.

- **Automatic hostnames** (P2): prefix + sequential number → `worker-1`,
  `worker-2`, … editable per row.
- **Optional sequential IPs** (P3): Management IP / iLO IP can be generated
  from a start address (`10.10.1.100`, `10.10.1.101`, …) or entered manually;
  generation never forces sequential addressing and every address stays
  editable.
- **Default credential** (P5): applied to every generated row, overridable per
  row.
- **Rack placement** (P4/P6): the U column is optional. Left blank, devices are
  installed unplaced and positioned later with the existing drag-and-drop rack
  editor (unchanged). If a U is provided, placement is validated (rack height +
  overlap) and the whole batch rolls back on conflict so the table can be
  fixed.

### API

- `POST /api/devices/bulk` gains an optional `items` array of per-row specs
  (hostname, management_ip, ilo_ip, credential ids, u_position). Without
  `items`, the 1.1.1 prefix/hostnames behavior is unchanged — fully backward
  compatible. `quantity` is now optional (only required for prefix mode).

### Upgrade notes

- No migration required. `docker compose` up/pull the 1.1.2 images.
- Default image tag is now `1.1.2`.

## 1.1.1 (2026-07-08)

Patch release. Fully backward compatible: the 1.0/1.1 `/api/devices` API,
exports, collectors, dashboard, search and audit log all keep working. The one
additive migration (0006) preserves all existing data.

### Data model — Device Template + Rack Device Instance (P5)

The device model is split into two concepts:

- **Device Template** — a reusable hardware model (vendor, model, CPU, memory,
  storage, firmware, NIC). Never holds deployment data.
- **Rack Device Instance** — an installed server: hostname, management IP,
  iLO IP, credentials, rack, U position, status. Many instances may reference
  one template.

Implementation: the existing `devices` table (which holds deployment data) was
renamed to `rack_device_instances`; its foreign keys
(snapshots/rack_units/collector_runs) follow the rename with no value rewrites,
so **existing rack layouts, snapshots and exports stay valid**. A new
`device_templates` table holds hardware models. Migration 0006 backfills one
**deduplicated** template per distinct (vendor, model) and links every existing
instance to it — one template + one instance per original device, no data loss.

- `GET/POST/PATCH/DELETE /api/device-templates` (read: any user; write: admin,
  audited). Deletion is blocked while instances reference the template.
- Creating a device accepts an optional `template_id`; vendor/model are
  inherited from the template when not set explicitly.
- Collectors keep writing **per-instance** snapshots; templates hold declared
  specs and are not overwritten by collection (so shared templates never
  thrash).
- UI: **Device Templates** admin page (hardware models); **Installed Devices**
  page manages instances and lets you pick a template.

### Other improvements

- **P1 — Rename**: "Bulk" rack creation is now **"Create Multiple Racks"**
  (button, dialog, tooltip, docs). API `POST /api/racks/bulk` unchanged.
- **P2 — Rack assignment workflow**: assign/remove devices without opening the
  spreadsheet editor. `PUT /api/devices/{id}/position` can now move a device
  into a different rack; new `DELETE /api/devices/{id}/position` uninstalls a
  device from its slot (keeps the device). Available inline in Installed
  Devices and via drag-and-drop in the rack editor.
- **P3 — Create Multiple Devices**: `POST /api/devices/bulk` installs many
  identical instances in one transaction with sequential hostname generation
  (prefix + zero-padded number) or explicit hostnames; duplicates skipped,
  errors reported. UI dialog in Installed Devices.
- **P4 — Drag-and-drop rack editing**: the rack layout editor is now a 42U
  drag-and-drop surface (same interaction as Rack View) — devices move
  directly with no automatic shifting, and an "Unplaced" palette assigns/removes
  devices. Replaces the number-input reordering.

### Upgrade notes

- `docker compose` up/pull the 1.1.1 images — migration 0006 runs automatically
  at startup and transforms existing devices into templates + instances.
- Default image tag is now `1.1.1`.

## 1.1.0 (2026-07-07)

Fully backward compatible with 1.0.0. All schema changes ship as additive
Alembic migrations (0003–0005) applied automatically on startup. No existing
API contract changed; new endpoints and optional parameters only.

### Core features

- **F1 — Inventory Export**: `GET /api/export?scope=device|rack|cluster|all`
  `&format=json|csv|xlsx`. Excel has one sheet per section (Devices, CPU,
  Memory, NIC, Storage, Firmware, Network, VM, Sensor); CSV is a zip with one
  file per section. Export buttons on Device Detail, Rack Detail and the
  Dashboard.
- **F2 — Collector Failure Diagnosis**: collector failures are categorized
  (`AUTH_FAILED`, `CONNECTION_TIMEOUT`, `HOST_UNREACHABLE`, `SSL_ERROR`,
  `DNS_FAILURE`, `HTTP_ERROR`, `REDFISH_SCHEMA_ERROR`, `SSH_ERROR`,
  `COLLECTOR_EXCEPTION`). CollectorRun stores `error_code` and
  `readable_message`; the Collector Management UI shows the code chip and
  readable text (migration 0003).
- **F3 — Unified Status / Health UI**: one `StatusPill` component defines the
  color/label language everywhere (Healthy/Online green, Warning orange,
  Critical/Offline red, Unknown gray, Refreshing blue; always icon + text).
- **F4 — Dashboard Summary**: `GET /api/dashboard/summary` with Total /
  Online / Warning / Critical / Offline / Unknown counts (Critical = health
  score in the Critical band). Five stat cards on the dashboard, visible to
  both roles.
- **F5 — Inventory Search / Filter**: `GET /api/devices/search` with free
  text (hostname, vendor, model, snapshot serials), dedicated field filters,
  cluster/rack/status filters and server-side pagination. New Inventory
  Search page in the sidebar.
- **F6 — Sensor Thresholds**: Redfish upper/lower thresholds are collected
  and displayed per sensor; "Threshold unavailable" otherwise
  (migration 0004).
- **F7 — Bulk Rack Creation**: `POST /api/racks/bulk` creates
  `PREFIX-1..N`; existing names are skipped and reported. Bulk Create dialog
  in Rack Management.

### Stretch features

- **F9 — Pagination**: optional `page`/`page_size` on `/api/devices`,
  `/api/users` and collector run logs (response shapes unchanged);
  `/api/devices/search` and `/api/audit` return paginated envelopes with
  totals.
- **F10 — Administrative Audit Log**: every admin CREATE/UPDATE/DELETE on
  clusters, racks, devices, credentials and users is recorded with who,
  when, and JSON old/new values (secrets redacted; migration 0005).
  Admin-only `GET /api/audit` and an Audit Log page with filters.

### Deferred to 1.2.0

- **F8 — Hardware Inventory Expansion** (PSU / Fan / GPU / PCI device
  tables): PSUs and fans are already visible as sensors; dedicated
  inventory tables need new collectors sections, schemas and UI tabs and
  were deferred to keep this release reviewable.
- **F11 — CSV Import**: bulk device registration with validation report.

### Upgrade notes

- `docker compose pull`/load new images and `docker compose up -d` —
  migrations 0003–0005 apply automatically at startup.
- New Python dependency: `openpyxl` (bundled in the backend image).
- Default image tag is now `1.1.0` (override with `IMAGE_TAG`).
