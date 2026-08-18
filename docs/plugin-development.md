# Rack Insight — Plugin Developer Guide

This is the official guide for building a Rack Insight **Plugin**. The Plugin
Platform lets you add a feature as an **independent service** — its own
container, with an optional **backend API** *and* its own **frontend** — **without
modifying Rack Insight Core**. You implement a small HTTP contract; the Core
discovers, health-checks, proxies, and embeds your plugin.

> Status: **Plugin Platform (v1)**. Backend + Frontend plugins are supported.
> The frontend is embedded as an **iframe** that the Core serves same-origin —
> deliberately **no** Module Federation / runtime bundle injection. Everything is
> backward-compatible: a backend-only plugin (no `ui` in its manifest) works
> exactly as before.

## Table of contents

1. [What is a Plugin?](#1-what-is-a-plugin)
2. [Architecture & responsibilities](#2-architecture--responsibilities)
3. [The single-origin rule](#3-the-single-origin-rule)
4. [Manifest specification](#4-manifest-specification)
5. [The UI descriptor](#5-the-ui-descriptor)
6. [Required endpoints](#6-required-endpoints)
7. [Health & readiness](#7-health--readiness)
8. [Backend API proxy](#8-backend-api-proxy)
9. [Frontend UI proxy (iframe)](#9-frontend-ui-proxy-iframe)
10. [Authentication & the plugin-UI cookie](#10-authentication--the-plugin-ui-cookie)
11. [Permissions & RBAC](#11-permissions--rbac)
12. [Using the Core inventory](#12-using-the-core-inventory)
13. [The Long-running Job Contract](#13-the-long-running-job-contract)
14. [Writing the frontend](#14-writing-the-frontend)
15. [API versioning](#15-api-versioning)
16. [Dockerfile](#16-dockerfile)
17. [Local development](#17-local-development)
18. [Docker Compose integration](#18-docker-compose-integration)
19. [Kubernetes deployment (the official path)](#19-kubernetes-deployment-the-official-path)
20. [Registering a plugin](#20-registering-a-plugin)
21. [Error handling](#21-error-handling)
22. [Logging](#22-logging)
23. [Security requirements](#23-security-requirements)
24. [Case study: a "Server Script Runner" plugin](#24-case-study-a-server-script-runner-plugin)
25. [Air-gapped deployment & future extension points](#25-air-gapped-deployment--future-extension-points)

---

## 1. What is a Plugin?

A Plugin is a standalone service (its own image/container) that:

- implements the **Plugin Contract** (a few HTTP endpoints), and
- is reachable from the Core by a stable URL (a Docker/Kubernetes **Service DNS
  name**, e.g. `http://example-plugin:8080` — never `localhost`).

The Core never runs plugin code in-process. It only talks HTTP to your plugin,
and the browser only ever talks to the Core.

```
                       Rack Insight Core
             Auth / RBAC / Inventory / Alerts / Audit
          Plugin Registry · API proxy · UI proxy · health
                              │
                       Plugin Contract
        ┌─────────────────────┼─────────────────────┐
   Example Plugin           Plugin B              Plugin C
  backend + UI + jobs      (backend-only)       (backend + UI)
     (container)            (container)          (container)
```

## 2. Architecture & responsibilities

| Layer        | Responsibility |
| ------------ | -------------- |
| **Core**     | Registry, configuration, health checks, metadata, status, **authentication**, **RBAC**, **inventory**, API proxy, **UI proxy**, audit, DB persistence |
| **Plugin backend** | Manifest, health/ready, plugin-specific API, jobs |
| **Plugin frontend**| A self-contained page served at `/ui/`, embedded by the Core as an iframe |
| **Core frontend**  | Top-level **Plugins** launcher (list + health + iframe), plus **Administration → Plugin Registry** |

The Core owns everything cross-cutting. Your plugin owns only its own feature.
Do not re-implement auth, RBAC, or inventory — reuse the Core's.

## 3. The single-origin rule

**The browser only ever uses the one Rack Insight origin (its Ingress).** It
never contacts a plugin's Kubernetes Service DNS name directly. This is the
central design rule and everything else follows from it:

- The plugin's **backend API** is reached via `…/proxy/…`.
- The plugin's **frontend** is reached via `…/ui/…`.
- The plugin authenticates through the Core; it never sees a login page.

Because there is a single origin, there is no CORS to configure, no second TLS
certificate, and no way for a browser to reach a plugin that the Core hasn't
authorized.

## 4. Manifest specification

Your plugin MUST serve `GET /plugin/manifest` returning JSON. camelCase is the
wire convention (snake_case is also accepted). Unknown fields are ignored, so
newer plugins never break an older Core.

```json
{
  "name": "example-plugin",
  "displayName": "Example Plugin",
  "version": "1.1.0",
  "apiVersion": "v1",
  "description": "Reference plugin: backend API, jobs, and an embedded UI.",
  "healthEndpoint": "/healthz",
  "readyEndpoint": "/readyz",
  "manifestEndpoint": "/plugin/manifest",

  "ui": { "type": "iframe", "path": "/ui/", "title": "Example Plugin" },

  "routes": [],
  "permissions": ["plugin.example.view", "plugin.example.execute"],
  "menus": []
}
```

- `name` — technical id, unique across plugins.
- `version` — **your plugin's** version (e.g. `1.4.2`).
- `apiVersion` — the **contract** version (`v1`). See §15.
- `ui` — optional; present ⇒ the plugin has a frontend (§5). Absent ⇒
  backend-only, and it simply won't appear in the Plugins launcher.
- `routes` / `permissions` / `menus` — reserved for future dynamic extension;
  declare them now if you like, but the Core does not consume them yet.

## 5. The UI descriptor

```json
"ui": { "type": "iframe", "path": "/ui/", "title": "Example Plugin" }
```

- `type` — only `iframe` is supported. (No Module Federation / bundle injection.)
- `path` — the plugin's UI entrypoint. The Core serves it same-origin at
  `/api/plugins/<name>/ui/`.
- `title` — the label shown in the Core's Plugins launcher and iframe header.

If `ui` is omitted the plugin is backend-only and the Core exposes only its API
proxy. Adding `ui` later is a non-breaking change.

## 6. Required endpoints

| Endpoint                | Purpose                                        |
| ----------------------- | ---------------------------------------------- |
| `GET /plugin/manifest`  | The contract (§4).                             |
| `GET /healthz`          | Liveness. `200` = alive.                       |
| `GET /readyz`           | Readiness. `200` = ready to serve.             |
| `GET /api/...`          | Your plugin-specific API.                      |
| `GET /ui/...`           | Your frontend (only if you declare `ui`).      |

See `plugins/example-plugin/app.py` for a complete implementation.

## 7. Health & readiness

The Core health-monitors every registered plugin on a short interval
(`PLUGIN_HEALTH_INTERVAL_SECONDS`, default 60s) and on demand. Status values:

```
HEALTHY     health endpoint returned 2xx
UNHEALTHY   unreachable / timeout / non-2xx
UNKNOWN     not yet checked
DISABLED    administratively disabled
```

**A plugin being UNHEALTHY never affects the Core.** All plugin calls are
timeout-bounded (`PLUGIN_REQUEST_TIMEOUT_SECONDS`, default 5s) and failures are
isolated — a dead plugin yields a clean `503`, never a Core `500` or a hang.

## 8. Backend API proxy

The browser never calls a plugin directly. The Core authenticates the user,
checks `plugin.proxy`, and forwards a minimal REST request (GET/POST):

```
GET  /api/plugins/{name}/proxy/{path}
POST /api/plugins/{name}/proxy/{path}
```

Example:

```
GET /api/plugins/example-plugin/proxy/api/status
        ↓  (Core auth + plugin.proxy)
GET http://example-plugin:8080/api/status
```

The Core does **not** forward its JWT to the plugin. If the plugin is unknown →
`404`; disabled or unreachable → `503`.

## 9. Frontend UI proxy (iframe)

If your manifest declares `ui`, the Core serves your frontend same-origin:

```
GET /api/plugins/{name}/ui/{path}
        ↓  (Core auth + plugin.proxy)
GET http://{plugin}:8080/ui/{path}
```

The Core sets `Content-Security-Policy: frame-ancestors 'self'` on the proxied
response so only the Core origin may frame it. In the Core UI, the plugin appears
under the top-level **Plugins** menu; selecting it mints the UI cookie (§10) and
loads `…/ui/` into a sandboxed `<iframe>`.

**Important:** the browser never learns your plugin's Service DNS name. It only
ever requests `…/ui/…` on the Core origin.

## 10. Authentication & the plugin-UI cookie

An iframe navigation (and the asset requests it triggers) cannot carry the SPA's
in-memory Bearer token. So, before loading the iframe, the Core mints a
short-lived cookie:

```
POST /api/plugins/ui-session      (Bearer-authenticated)
  → Set-Cookie: ri_plugin_ui=<short-lived JWT>;
                Path=/api/plugins; HttpOnly; SameSite=Strict
```

- The **UI proxy** and the **API proxy** both accept this cookie *or* a Bearer
  token (`get_current_user_flexible`).
- `SameSite=Strict` + `Path=/api/plugins` makes it CSRF-safe and confines it to
  plugin traffic.
- Your frontend simply uses `fetch(..., { credentials: "same-origin" })`; the
  cookie is sent automatically. You never handle tokens yourself.

## 11. Permissions & RBAC

Plugins live behind the Core's existing authentication and RBAC — **do not build
your own.** The Core exposes three core permissions:

- `plugin.view` — see the registry/launcher and open a plugin UI.
- `plugin.manage` — register / enable / disable / remove.
- `plugin.proxy` — call a plugin's API/UI through the Core proxy.

For plugin-specific authorization, use the reserved namespace
`plugin.<name>.<action>`, e.g. `plugin.example.view`, `plugin.example.execute`.
Declare them in your manifest's `permissions` list. (Automatic seeding of
plugin-declared permissions into RBAC is a future enhancement; today the proxy is
gated by the core `plugin.proxy` permission, and you can enforce finer-grained
checks inside your plugin based on what the Core has already authenticated.)

## 12. Using the Core inventory

**A plugin must never replicate the Core inventory in its own database.** The
Core is the single source of truth for servers. It exposes a read-only view for
plugins, reachable through the same-origin proxy (so the UI cookie works):

```
GET /api/plugins/inventory/servers
```

Each row is identity/placement only — **never credentials**:

```json
{
  "id": "…", "hostname": "srv-01", "displayName": null,
  "managementIp": "10.0.0.5", "deviceType": "SERVER",
  "vendor": "Dell", "model": "R760", "status": "ONLINE",
  "rack": "R1", "cluster": "C1"
}
```

Your plugin references a server by the opaque `id`. If it needs to *act* on the
server (e.g. connect to it), that capability belongs to the Core or a future
Core-mediated contract — the plugin never holds device credentials (§23).

## 13. The Long-running Job Contract

Anything that takes more than a moment should be a **job**: the client starts it,
then polls. The reference plugin implements this contract in memory; a real
plugin persists jobs in **its own** database and runs them in a worker.

**States:** `queued → running → completed | failed | cancelled`.

| Endpoint                       | Behavior                                            |
| ------------------------------ | --------------------------------------------------- |
| `POST /api/jobs`               | Create a job. Returns `202` with `{ id, state: "queued", … }`. |
| `GET  /api/jobs`               | List jobs.                                          |
| `GET  /api/jobs/{id}`          | Job status: `{ id, state, progress, … }`.           |
| `GET  /api/jobs/{id}/results`  | Results — only when `completed` (else `409`).       |
| `POST /api/jobs/{id}/cancel`   | Request cancellation (cooperative; else `409` if terminal). |

Clients reach these through the Core proxy, e.g.
`POST /api/plugins/<name>/proxy/api/jobs`. Design guidance:

- Return `202 Accepted` on create; never block the request until the work is done.
- Make status cheap and frequent-poll-safe.
- Cancellation is cooperative — check a flag between steps; don't kill threads.
- Persist jobs (a real plugin), so a restart doesn't lose state.

## 14. Writing the frontend

Keep it simple and self-contained. The reference UI is a single
`ui/index.html` (inline CSS/JS, no build step) served by FastAPI's `StaticFiles`.
You may use any framework, but the page must:

1. **Derive the proxy base from its own URL** — do not hardcode your plugin name.
   You are served at `/api/plugins/<name>/ui/…`, so:

   ```js
   const pluginRoot  = location.pathname.replace(/\/ui(\/.*)?$/, ""); // /api/plugins/<name>
   const proxyBase   = pluginRoot + "/proxy";                          // your backend API
   const inventory   = pluginRoot.replace(/\/[^/]+$/, "") + "/inventory/servers";
   ```

2. **Send credentials** so the UI cookie rides along:

   ```js
   fetch(proxyBase + "/api/jobs", { credentials: "same-origin", method: "POST", … });
   ```

3. **Escape untrusted data** before inserting it into the DOM.

The Core embeds the page with `sandbox="allow-scripts allow-same-origin
allow-forms"` — enough to run and call the proxy, but not to navigate the top
window or open popups.

## 15. API versioning

`apiVersion` describes the **contract**, not your build. The current contract is
`v1`. When the Core introduces a breaking contract change it will support `v1`
and `v2` side by side; you migrate when ready.

```
Plugin Version : 1.4.2     (your service)
API Version    : v1        (the Core contract you implement)
```

Adding manifest fields (like `ui`) is forward-compatible and never breaks an
older Core.

## 16. Dockerfile

Build a self-contained image (no runtime internet access), mirroring the Core:

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
```

`COPY . .` bundles your `ui/` directory into the image, so the frontend ships
with the backend as one artifact.

## 17. Local development

```bash
cd plugins/example-plugin
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8080
curl localhost:8080/plugin/manifest
open  http://localhost:8080/ui/          # the frontend, standalone
```

## 18. Docker Compose integration

Add your plugin as a service and register it with the Core via config.

```yaml
# deploy/local/docker-compose.yml
  example-plugin:
    image: rack-insight-plugin-example:1.1.0
    healthcheck:
      test: ["CMD","python","-c","import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=3)"]
    restart: unless-stopped
```

The Core does **not** `depends_on` any plugin (failure isolation). Register the
plugin by editing `deploy/local/plugins.json` (mounted into the backend as
`PLUGINS_CONFIG_FILE=/config/plugins.json`):

```json
[
  { "name": "example-plugin", "endpoint": "http://example-plugin:8080", "enabled": true }
]
```

## 19. Kubernetes deployment (the official path)

The reference plugin ships as `deploy/kubernetes/base/plugins/example-plugin.yaml`
(Deployment + Service); registration is via the shared plugins ConfigMap
`deploy/kubernetes/base/config/plugins-configmap.yaml` (mounted into the backend
as `PLUGINS_CONFIG_FILE`). The Core reaches the plugin at its **Service DNS**
name `http://<plugin>:8080` — identical to compose — so nothing in the Core
changes between environments. Scale replicas freely; the Service load-balances.

Single repo, single GitOps flow:

```
1. Copy plugins/example-plugin as a template
2. Write your plugin (backend + optional ui/, implement §4–13)
3. docker build your image (immutable tag — never :latest)
4. Local test (uvicorn / docker; curl /plugin/manifest, /healthz, /ui/)
5. Add k8s Deployment+Service manifest + a plugins-ConfigMap entry
6. git push to a feature/* branch
7. Open a Pull Request  → CI builds & tests (no deploy)
8. Merge to main        → CI builds & pushes your image (commit-SHA tag)
9. CI updates the overlay image tags (GitOps commit on main)
10. ArgoCD (tracks main) detects the change and syncs the cluster
11. Your plugin is deployed; the Core registers and health-checks it
```

## 20. Registering a plugin

Two equivalent ways:

1. **Configuration (recommended, air-gap friendly).** Add an entry to
   `PLUGINS_CONFIG` (inline JSON) or `PLUGINS_CONFIG_FILE` (a JSON file /
   ConfigMap). Config-declared plugins are re-seeded on every Core start.
2. **API / UI.** `POST /api/plugins` (or **Administration → Plugin Registry →
   Register Plugin**) with `{ "name", "endpoint" }`.

The Core fetches your manifest on registration to fill in version / api version /
display name / UI descriptor.

## 21. Error handling

- Return correct HTTP status codes from your endpoints; the proxy relays them.
- Keep endpoints fast; the Core enforces a request timeout. Long work → jobs (§13).
- Never assume the Core forwards its own auth token — it doesn't.
- A plugin that is down, slow, or malformed becomes `UNHEALTHY`; it never breaks
  the Core.

## 22. Logging

Log to stdout (12-factor); the container runtime collects it. **Never log
secrets.**

## 23. Security requirements

These are requirements, not suggestions:

- **No plaintext credentials in the plugin.** Do not design your plugin to store
  device/user credentials in plaintext (or in a ConfigMap). Secrets belong to the
  Core / Kubernetes Secrets; a plugin should not need them.
- **Plugin ConfigMaps are for non-sensitive configuration only.**
- **Never build a shell command from untrusted input.** Do not
  `os.system(user_input)` or concatenate strings into a shell. If you must run a
  subprocess, pass an **argument list** (`subprocess.run([...], shell=False)`),
  validate/allow-list inputs, and never interpolate them into a command string.
- **Validate everything crossing the boundary** — request bodies, job parameters,
  and any server id you receive.
- **Least privilege** — run the container as non-root, read-only filesystem where
  possible, no extra Linux capabilities.
- **The plugin never bypasses the Core** — no direct browser access, no direct
  inventory DB, no second auth system.

## 24. Case study: a "Server Script Runner" plugin

A common request is "let operators run a maintenance script against a server."
Here is how that maps onto the platform **safely** — a design, not runnable code:

**Shape.** A backend + UI + jobs plugin. The UI lists servers (from
`/api/plugins/inventory/servers`), lets the operator pick a script from a
**curated, plugin-owned catalog**, and starts a job. The job streams progress;
results are fetched when complete.

**Do this**

- Keep an **allow-list** of vetted scripts shipped inside the plugin image. The
  operator selects one by id; they do **not** upload or paste arbitrary code.
- Parameterize scripts through a **typed, validated** schema, and pass parameters
  as an **argument vector**, never string-concatenated into a shell.
- Run each execution as a **job** (§13) with a timeout and cooperative cancel.
- Target a server by the opaque inventory `id`. Connecting to the server (and the
  credentials that requires) is the Core's responsibility, not the plugin's —
  the plugin holds **no** device credentials.
- Gate execution behind `plugin.<name>.execute`, distinct from `.view`.
- Audit every run (who, which script, which target, outcome).

**Never do this**

- `os.system(uploaded_script)` or `subprocess.run(f"ssh {host} {cmd}", shell=True)`
  — arbitrary code + command injection.
- Accepting a raw script body from the browser and executing it.
- Storing SSH/iLO passwords in the plugin's DB or a ConfigMap.
- Opening SSH from the plugin using credentials it fetched and cached.

> This release does **not** ship a Server Script Runner or any SSH capability.
> The section documents the intended architecture so that, when such a plugin is
> built, it is built the safe way from day one.

## 25. Air-gapped deployment & future extension points

**Air-gapped:**

- Build your plugin image on an internet-connected machine; the resulting image
  must run with **no** runtime internet access (pin dependencies, no runtime
  downloads).
- Ship it inside the Rack Insight offline bundle
  (`deploy/offline/build_and_export.sh` builds and exports plugin images too).
- Registration uses local configuration only — no external service discovery.
- Never use `:latest`; use immutable, content-addressed tags.

```
RackInsight Bundle
├── Core / Frontend images
├── Plugin images (backend + bundled ui/)
├── deploy/local/plugins.json, deploy/kubernetes/*
├── docker-compose.yml
└── load/install scripts
```

**Reserved for future releases (not consumed today):**

- Plugin-declared **permissions** auto-seeded into RBAC.
- Plugin-declared **menus/routes** surfaced dynamically in the Core frontend.
- **Plugin events → Core Event Contract → Alert Engine** (a plugin emits an
  event; the Core's Event/Alert pipeline turns it into an alert). The event model
  already tolerates `plugin.*` event types — `AlertPolicy` maps unrecognized
  types to the `Other` category — so this can be added without a contract change.
