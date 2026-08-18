# Changelog

All notable changes to Rack Insight. See `docs/RELEASE_NOTES.md` for the full
notes of each release.

## [Unreleased] — Kubernetes / ArgoCD deployment architecture + repo cleanup

Deployment-architecture migration and repository reorganization only — **no
application code, API, DB schema, RBAC, alert, collector, inventory, or
plugin-contract changes.** The app version is deliberately not bumped.

### Repository reorganized (app / deploy / docs)

- **All deployment concerns consolidated under `deploy/`**: `local/` (Docker
  Compose, moved from the repo root + `docker/`), `kubernetes/`, `argocd/`,
  `offline/` (moved from `scripts/offline/`). The root is now just
  `backend/ frontend/ plugins/ deploy/ docs/ + README + CHANGELOG`.
- **Removed the orphan `redfish-proxy/`** (a TLS shim to a mock Redfish server
  that does not exist here — not wired to anything) and its opt-in k8s template.
- **README slimmed** to a concise overview + quickstart + docs index; the
  per-release "What's new" wall was removed (history lives in `CHANGELOG.md` /
  `docs/RELEASE_NOTES.md`).
- **Docs split** by intent: `docs/development.md` (run/dev/migrations),
  `docs/deployment.md` (k8s/ArgoCD, renamed from kubernetes-deployment.md),
  `docs/architecture.md` (design/features), `docs/plugin-development.md`;
  `deploy/README.md` indexes the deployment folder.
- Compose/offline relative paths and Dockerfile comments updated for the new
  locations; container images and manifests are unchanged.

### Added
- **Kustomize manifests** (`deploy/kubernetes/base` + `overlays/testbed`):
  namespace, ConfigMap, `secret.example.yaml`, plugins ConfigMap, PostgreSQL
  StatefulSet + PVC + headless Service, Redis Deployment + Service, backend
  Deployment + Service (probes on `/api/health`, DB-wait init container,
  plugins ConfigMap mount), frontend Deployment + Service (probes on `/`),
  example-plugin Deployment + Service, and an Ingress replacing the compose
  reverse-proxy routing (`/api`,`/docs`,`/openapi.json`→backend, `/`→frontend).
- **ArgoCD Application** (`deploy/argocd/application.yaml`) tracking **main only**
  at the testbed overlay (no ApplicationSet / PR preview).
- **CI/CD** (`.github/workflows/ci.yml`): PRs build+test; pushes to main build &
  push commit-SHA-tagged images and GitOps-bump the overlay tags (immutable
  tags — never `:latest`).
- **Optional** in-cluster redfish-proxy template (`deploy/kubernetes/optional/`),
  not part of the base build.
- Docs: `docs/kubernetes-deployment.md`; README rewritten around the new
  Local-dev (Compose) vs Testbed (Kubernetes/ArgoCD) model; plugin guide updated
  with the GitOps plugin lifecycle.

### Changed
- Kustomize chosen over Helm (built into kubectl + ArgoCD, no chart repo →
  air-gap friendly); base+overlays for environment separation.
- Docker Compose reframed as **local development only** (relabeled header + docs);
  Kubernetes is the official testbed/production runtime.
- Service DNS names (`postgres`, `redis`, `example-plugin`) match the app's
  existing env defaults, so **no application code changed** for k8s.

## [1.4.0] - 2026-07-10 — Plugin Architecture Foundation

Foundation for extending Rack Insight with independent plugin backends without
modifying Core. Additive migration 0012; fully backward compatible. No MSA
rewrite — existing Cluster/Rack/Device/Discovery/Collector/Lifecycle/Alert/
Audit/Access-Management features are unchanged and stay in Core.

### Added
- **Plugin Contract** (`schemas/plugin.py`): `GET /plugin/manifest`
  (name/displayName/version/apiVersion/health/ready), camelCase-or-snake_case,
  forward-compatible.
- **Plugin Registry** (`services/plugin_registry.py`, `models/plugin.py`,
  migration 0012 `plugins` table): configuration (endpoint/enabled) kept
  separate from runtime state (status / last_health_check / last_success /
  last_failure / reason).
- **Config-based registration** (`PLUGINS_CONFIG` inline JSON or
  `PLUGINS_CONFIG_FILE` / ConfigMap), seeded idempotently at startup. Air-gap
  friendly; no external service discovery.
- **Health monitor** (`scheduler/plugin_monitor.py`): dedicated, isolated
  background probe. Statuses HEALTHY / UNHEALTHY / UNKNOWN / DISABLED. A dead,
  slow, or malformed plugin never affects Core (bounded timeouts, per-plugin
  isolation).
- **REST proxy foundation**: `GET|POST /api/plugins/{name}/proxy/{path}` — Core
  authenticates + checks `plugin.proxy`, then forwards; unknown → 404, disabled/
  unreachable → 503 (never Core 500). Core JWT is not forwarded to plugins.
- **Registry API**: `GET/POST/PATCH/DELETE /api/plugins`, `GET /api/plugins/{id}`,
  `POST /api/plugins/{id}/health-check`.
- **RBAC**: `plugin.view` / `plugin.manage` / `plugin.proxy` seeded into system
  roles (Viewer: view; Operator: view+proxy; Administrator: all). Namespace
  `plugin.<name>.<action>` reserved for plugin-declared permissions.
- **Audit**: plugin register/enable/disable/remove and health transitions are
  audited (system-actor helper for monitor-driven changes).
- **Example Plugin** (`plugins/example-plugin/`): standalone FastAPI container
  (`/plugin/manifest`, `/healthz`, `/readyz`, `/api/status`, `/api/echo`) with
  Dockerfile, requirements, README.
- **Deployment**: `example-plugin` in docker-compose (image + build override),
  `deploy/plugins.json` ConfigMap-style file mounted into the backend,
  `deploy/kubernetes/example-plugin.yaml` (Deployment + Service + ConfigMap),
  offline export bundles plugin images.
- **Frontend**: Administration → **Plugins** page (table with name/version/api
  version/status/endpoint/last-check/enabled, detail dialog, register,
  enable/disable, health-check), permission-gated; header/sidebar unchanged.
- **Docs**: `docs/plugin-development.md` (full plugin developer guide).

### Notes
- Dynamic UI injection (Module Federation, runtime bundles, iframes) is out of
  scope, reserved for a future release. Plugin events → Alert Engine is a
  documented future extension point (the event model already tolerates unknown
  `plugin.*` event types via `AlertPolicy`'s `Other` fallback).

## [1.3.1] - 2026-07-10 — Alert Engine responsibility split

Maintainability patch. Same architecture and behaviour as 1.3.0; the Alert
Engine is now a thin orchestrator with the business rules extracted into small
pure helpers. Additive migration 0011; backward compatible.

### Added
- **AlertPolicy** (`services/alert_policy.py`) — pure mapping from an Event to
  its alert behaviour (category, severity, auto-resolve). No DB, no side
  effects; future severity rules have a single home.
- **AlertBuilder** (`services/alert_builder.py`) — constructs the Alert model
  only. No resolve/dedupe/history/DB access.
- **Alert category** now distinct from event type: `Alert.event_type` (what
  happened) + `Alert.category` (operational domain: Hardware, Firmware,
  Connectivity, Collector, Credential, Health). The UI filters by category; the
  event type is shown per row. Alerts API gains an `event_type` filter and
  returns both fields.
- **Event.subject** — the Event Engine records what changed (sensor name, DIMM
  slot, firmware component…); the Alert Engine reuses it instead of parsing
  JSON details.

### Changed
- Alert Engine reduced to orchestration: persist events → resolve counterparts
  → dedupe → AlertPolicy → AlertBuilder → persist → record history. Lifecycle
  queries key off `event_type` (was `category`).
- Migration 0011 backfills existing alerts (`event_type = category`, then
  reclassifies `category` to the operational domain).

### Preserved
- One event → one alert; recovery events create already-resolved INFO alerts;
  Hardware/Firmware alerts require manual resolve; state alerts auto-resolve;
  active state alerts deduplicated; history immutable; existing APIs unchanged.

## [1.3.0] - 2026-07-10 — Operations & Alert Center

### Added
- Operations pipeline: Collector → Inventory Snapshot → **Event Engine** →
  **Alert Engine** → Frontend. The collector only stores snapshots; the Event
  Engine compares snapshot N-1 vs N and is the only producer of events; the
  Alert Engine owns the alert lifecycle.
- Event types: HardwareChanged, FirmwareChanged, DeviceOffline,
  DeviceRecovered, SensorThresholdExceeded, SensorRecovered, CollectorFailed,
  CredentialFailed, NetworkReachabilityChanged (extensible).
- Alerts: INFO/WARNING/CRITICAL, ACTIVE/RESOLVED. Hardware/Firmware alerts
  resolve manually; state alerts auto-resolve on recovery. Configurable
  consecutive-failure threshold (default 3).
- Permanent, immutable **Device History** (firmware upgrades, hardware
  replacements, collector failures, manual resolves).
- Health model: `GET /api/devices/{id}/health` (overall health, sensor
  groups, storage/memory/network health, health timeline) + Device Detail
  **Health** tab.
- **Alert Center** UI: top-level Alerts section (Alerts + History pages),
  filterable alert table, header notification bell with unread count
  (UI-only notifications), reusable AlertSeverityBadge / AlertStatusBadge /
  Timeline / **DiffViewer** / HistoryCard / HealthSummaryCard components.
- Operations dashboard: alert cards, latest alerts, critical devices, recent
  hardware/firmware changes (cluster browsing unchanged).
- APIs: /api/alerts, /api/alerts/{id}, /api/alerts/{id}/resolve,
  /api/history, /api/history/device/{id}, /api/dashboard/alerts,
  /api/dashboard/health, /api/lifecycle/alert-settings.
- Retention categories `resolved_alerts` and `history` (history ships
  disabled = permanent). Migration 0010 (additive).
- RBAC permissions `alert.view`, `alert.resolve`, `history.view`.

### Changed
- Dashboard is operations-first; Device Detail tabs are Overview / Health /
  Hardware / Firmware / Network / Storage / VM / History.
- Background scheduler retries all enabled devices (not only ONLINE) and runs
  the full pipeline.

### Removed
- Drift UI (Drift tab). Hardware changes are Alerts; History stores the
  permanent record. The `/api/devices/{id}/drift` endpoint remains for
  backward compatibility.

## [1.2.2] - 2026-07-10 — Administration UX & Navigation

- Grouped, collapsible sidebar (Inventory / Operations / Administration /
  Access Management) with persisted expand state.
- Role assignment moved into the User Group editor; standalone Role Bindings
  page removed (table + APIs preserved).
- Role Details page (permissions, bound groups, effective user count).
- Standalone Permissions page removed (permissions live in the Role editor).

## [1.2.1] - 2026-07-10 — Access Management (RBAC)

- Full RBAC: User → User Group → Role Binding → Role → Permissions.
- System roles Administrator / Operator / Viewer + custom roles; centralized
  `RequirePermission` guard (HTTP 403); permission-driven sidebar and routes.
- Users extended with display name / email / status. Migration 0009.

## [1.2.0] - 2026-07-08 — Operational Automation & Discovery

- SNMP Discovery + Import Wizard, Initial Collection, Inventory Drift
  Detection, Firmware Compliance, Lifecycle & Retention. Migration 0008.

## [1.1.3] - Stabilization patch

- Rack placement integrity fixes (orphan units, overlap validation), bulk
  provisioning validation, hostname/template consistency.

## [1.1.2] - Provisioning wizard

- Bulk provisioning wizard with editable review table, hostname generation,
  sequential IPs, default credentials.

## [1.1.1] - Device Templates

- Device model split into Device Template + Rack Device Instance
  (migration 0006), bulk install, rack drag & drop preserved.

## [1.1.0] - Admin & operations features

- Export (JSON/CSV/XLSX), collector diagnostics, unified status model,
  dashboard, inventory search, sensor thresholds, bulk racks, audit log.

## [1.0.x] - Initial releases

- Inventory MVP: clusters/racks/devices, Redfish/SSH/virsh/Cisco collectors,
  snapshot-based inventory, JWT auth, air-gapped deployment, Admin Console,
  Alembic migration framework.
