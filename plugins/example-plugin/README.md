# Rack Insight — Reference Plugin

A complete, standalone reference plugin: **backend API + long-running jobs + an
embedded frontend**. It shares no code with the Core and runs in its own
container. Copy this directory as the starting point for a new plugin — see
[`docs/plugin-development.md`](../../docs/plugin-development.md) for the full
contract.

## What it demonstrates

- The **Plugin Contract**: manifest, health/ready, a backend API.
- A **UI descriptor** in the manifest (`ui.type = "iframe"`) and a
  self-contained frontend served under `/ui/`, which the Core embeds as a
  same-origin iframe.
- The **Long-running Job Contract**: create a job, poll its state, fetch results,
  cancel it.
- **Reusing the Core inventory** — the UI lists servers from the Core (never its
  own copy) and targets a job at one.

## Endpoints

| Endpoint                       | Purpose                                             |
| ------------------------------ | --------------------------------------------------- |
| `GET  /plugin/manifest`        | Plugin metadata, incl. the `ui` descriptor          |
| `GET  /healthz`                | Liveness (200 = alive)                              |
| `GET  /readyz`                 | Readiness (200 = ready)                             |
| `GET  /api/status`             | Example backend API                                 |
| `POST /api/echo`               | Example POST endpoint (echoes its body)             |
| `POST /api/jobs`               | Create a job → `202`, `state=queued`                |
| `GET  /api/jobs`               | List jobs                                           |
| `GET  /api/jobs/{id}`          | Job status (`queued/running/completed/failed/cancelled`) |
| `GET  /api/jobs/{id}/results`  | Job results (only when `completed`)                 |
| `POST /api/jobs/{id}/cancel`   | Request cooperative cancellation                    |
| `GET  /ui/`                    | Self-contained frontend (embedded as an iframe)     |

## Local development

```bash
cd plugins/example-plugin
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8080
curl localhost:8080/plugin/manifest
```

## Build (internet-connected machine)

```bash
docker build -t rack-insight-plugin-example:1.1.0 plugins/example-plugin
```

## Run with the Core (docker compose)

The Core registers this plugin via `PLUGINS_CONFIG_FILE` and reaches it at the
Docker/Kubernetes service DNS name `http://example-plugin:8080` — never
`localhost`. Bring the whole stack up with:

```bash
docker compose -f deploy/local/docker-compose.yml up -d
```

Then, in the Rack Insight UI:

- **Plugins** (top-level menu) → open **Example Plugin** to use its embedded UI.
- **Administration → Plugin Registry** to see status / enable / disable / health.

## How the frontend reaches the plugin

The browser never talks to the plugin directly and never learns its Service DNS
name. The Core serves the plugin UI same-origin and proxies its API:

```
Browser ──▶ /api/plugins/example-plugin/ui/         (Core UI proxy)   ──▶ plugin /ui/
Plugin JS ─▶ /api/plugins/example-plugin/proxy/...   (Core API proxy)  ──▶ plugin /api/...
Plugin JS ─▶ /api/plugins/inventory/servers          (Core inventory)  ──▶ Core devices
```

The iframe authenticates with a short-lived, `SameSite=Strict`, HttpOnly cookie
(`ri_plugin_ui`) the Core mints for it — an iframe cannot carry the SPA's Bearer
token. See the developer guide for the full flow.
