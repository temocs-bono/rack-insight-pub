# Architecture

Rack Insight is a web-based hardware & firmware inventory and operations platform
for datacenter servers (HPE iLO / Redfish) and switches (Cisco), with an
extensible plugin system.

## Application architecture

```
Browser ── React + TypeScript (Vite, TailwindCSS, TanStack Query)
   │
 Ingress / nginx ──► FastAPI (REST, JWT auth, RBAC)
                        │
                  Service layer ──► Collector layer (async, parallel, plugin-based)
                        │                ├── Redfish  (HPE iLO)
                        │                ├── SSH      (Linux OS data)
                        │                ├── Virsh    (VM inventory)
                        │                └── Cisco    (NX-OS / IOS-XE)
                        │
                  PostgreSQL (append-only snapshots)
                        │
                      Redis (TTL cache)
```

The operations pipeline sits on top of the collectors:

```
Collector ─► Inventory Snapshot ─► Event Engine ─► Alert Engine ─► UI
```

- The **collector** only stores snapshots.
- The **Event Engine** compares snapshot N-1 vs N and emits events.
- The **Alert Engine** turns events into alerts and manages their lifecycle
  (`AlertPolicy` decides category/severity/auto-resolve, `AlertBuilder`
  constructs the alert).

## Key policies

- **Snapshot model** — every collector run creates a new snapshot; the UI reads
  the latest. Old snapshots are retained for history/drift.
- **Fail-safe** — if all collectors fail (retries + timeout), no snapshot is
  written and the previous inventory stays intact.
- **Cache** — reads go Redis → DB → Redis; refresh re-collects and repopulates.
- **Scheduler** — enabled devices are re-collected on an interval.
- **Health score** — Online + collector success + power/fan/storage/firmware/
  sensor OK → Healthy / Warning / Critical.
- **Security** — JWT access/refresh tokens, bcrypt password hashes, iLO/SSH/SNMP
  credentials encrypted at rest (Fernet); secrets never logged or returned.
- **RBAC** — User → User Group → Role Binding → Role → Permissions. Built-in
  Administrator / Operator / Viewer roles plus custom roles; every endpoint is
  guarded by a single `RequirePermission(code)` dependency (HTTP 403 on denial).
- **Schema** — managed exclusively by Alembic; `alembic upgrade head` runs at
  startup, so a container's schema always matches its code.

## Features by area

- **Inventory** — Clusters, Racks (42U drag-and-drop), Devices, Device
  Templates. Register servers/switches with vendor/model/IP/credentials and
  browse hardware, firmware, network, storage and VM inventory.
- **Operations** — SNMP Discovery + Import Wizard, per-device Collector control,
  Lifecycle/retention policies, and the **Alert Center** (alerts + immutable
  device history, notification bell, before→after diff viewer).
- **Access Management** — Users, User Groups (members + role assignment), Roles
  (with a Role Details page); permissions managed inside the Role editor.
- **Administration** — Credentials (encrypted, write-only), **Plugins** (see
  [plugin-development.md](plugin-development.md)).
- **Dashboard** — operational overview (alert counts, offline/healthy devices,
  recent hardware/firmware changes) plus Cluster → Rack → Device browsing.

For per-release detail see [`../CHANGELOG.md`](../CHANGELOG.md) and
[`RELEASE_NOTES.md`](RELEASE_NOTES.md).
