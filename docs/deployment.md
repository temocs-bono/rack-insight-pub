# Rack Insight — Kubernetes / ArgoCD Deployment

The official testbed and production runtime for Rack Insight is **Kubernetes**,
deployed via **GitOps with ArgoCD**. Docker Compose is retained only for local
development (see the README).

```
Developer ──► feature/* ──► Pull Request ──► main
                                              │
                                              ▼
                                             CI  (build • test • image push)
                                              │
                                    Container Registry
                                              │
                                   GitOps manifest update (image tag = commit SHA)
                                              │
                                            ArgoCD  (tracks main only)
                                              │
                                       Kubernetes Cluster
                        ┌───────────────┬─────┴─────┬───────────────┐
                     Frontend        Backend    PostgreSQL/Redis   Plugins
                                                              (Redfish Proxy: optional)
```

## Why Kustomize (not Helm)?

Kustomize is built into `kubectl` and natively supported by ArgoCD, so it adds
**no extra binary and no chart repository** — the right fit for **air-gapped**
clusters. `base/` holds environment-agnostic manifests; `overlays/<env>/` pin
per-environment image tags, hostnames, replicas and storage classes. Helm would
require a chart repo (or bundling `helm` + charts into the air-gap payload) for
no benefit at this size.

## Repository layout

```
deploy/
├── local/                        # Docker Compose (local development only)
├── kubernetes/
│   ├── base/                     # environment-agnostic manifests
│   │   ├── namespace.yaml
│   │   ├── config/               # ConfigMap + plugins ConfigMap
│   │   ├── secrets/secret.example.yaml   # EXAMPLE ONLY (never real secrets)
│   │   ├── postgres/             # StatefulSet + headless Service (+ PVC template)
│   │   ├── redis/                # Deployment + Service (ephemeral cache)
│   │   ├── backend/              # Deployment + Service
│   │   ├── frontend/             # Deployment + Service
│   │   ├── plugins/example-plugin.yaml
│   │   ├── ingress.yaml
│   │   └── kustomization.yaml
│   └── overlays/
│       └── testbed/kustomization.yaml     # ArgoCD points here
├── argocd/
│   └── application.yaml          # ArgoCD Application (tracks main)
└── offline/                      # build/export & load images for air-gap
```

## Components, ports & health

| Component      | Kind         | Service DNS            | Port | Health probe            |
| -------------- | ------------ | ---------------------- | ---- | ----------------------- |
| frontend       | Deployment   | `frontend`             | 80   | `GET /`                 |
| backend        | Deployment   | `backend`              | 8000 | `GET /api/health`       |
| postgres       | StatefulSet  | `postgres` (headless)  | 5432 | `pg_isready`            |
| redis          | Deployment   | `redis`                | 6379 | `redis-cli ping`        |
| example-plugin | Deployment   | `example-plugin`       | 8080 | `GET /healthz`,`/readyz`|

Service-to-service traffic uses **Service DNS only** (`postgres`, `redis`,
`example-plugin`). Because the app's `DATABASE_URL` / `REDIS_URL` defaults
already use the hostnames `postgres` / `redis`, **no application code changed**.
The browser reaches everything through one Ingress origin, and the frontend
calls the API with the relative path `/api`, so no runtime backend URL is
needed.

## Prerequisites

- A Kubernetes cluster and `kubectl` (v1.27+; Kustomize is built in).
- An Ingress controller. **Check which one you have** and set
  `spec.ingressClassName` + annotations in `base/ingress.yaml` accordingly:
  ```bash
  kubectl get ingressclass
  ```
- A container registry reachable by the cluster (internal registry for
  air-gapped).
- ArgoCD installed in the cluster (for the GitOps path).

## Configuration (env → ConfigMap / Secret)

Every backend setting is an environment variable (`backend/config/settings.py`).

**ConfigMap** (`rack-insight-config`, non-sensitive):
`DEBUG, REDIS_URL, CACHE_TTL_SECONDS, ACCESS_TOKEN_EXPIRE_MINUTES,
REFRESH_TOKEN_EXPIRE_DAYS, DEFAULT_ADMIN_USERNAME, COLLECTOR_TIMEOUT_SECONDS,
COLLECTOR_RETRY_COUNT, SCHEDULER_ENABLED, SCHEDULER_INTERVAL_SECONDS,
CORS_ORIGINS, PLUGINS_CONFIG_FILE, PLUGIN_HEALTH_ENABLED,
PLUGIN_HEALTH_INTERVAL_SECONDS, POSTGRES_USER, POSTGRES_DB`.

**Secret** (`rack-insight-secrets`, sensitive — never committed):
`JWT_SECRET_KEY, ENCRYPTION_KEY, DEFAULT_ADMIN_PASSWORD, DATABASE_URL,
POSTGRES_PASSWORD`.

**Plugins ConfigMap** (`rack-insight-plugins`) is mounted into the backend at
`/config/plugins.json` (`PLUGINS_CONFIG_FILE`). Add a plugin by editing this
ConfigMap — no Core image change.

Generate real secret values:
```bash
openssl rand -hex 32                                          # JWT_SECRET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # ENCRYPTION_KEY
```

## Manual deployment (kubectl + Kustomize)

```bash
# 1) Namespace + create the real Secret (NOT committed to git).
kubectl create namespace rack-insight
cp deploy/kubernetes/base/secrets/secret.example.yaml /tmp/secret.yaml
#   edit /tmp/secret.yaml with real values, then:
kubectl apply -n rack-insight -f /tmp/secret.yaml

# 2) Point the overlay images at your registry (immutable tags — never latest):
cd deploy/kubernetes/overlays/testbed
kustomize edit set image rack-insight-backend=<REGISTRY>/rack-insight-backend:<TAG>
kustomize edit set image rack-insight-frontend=<REGISTRY>/rack-insight-frontend:<TAG>
kustomize edit set image rack-insight-plugin-example=<REGISTRY>/rack-insight-plugin-example:<TAG>

# 3) Render + apply.
kubectl apply -k deploy/kubernetes/overlays/testbed

# 4) Verify.
kubectl get pods,svc,endpoints -n rack-insight
kubectl get ingress -n rack-insight
```

Open `http://rack-insight.testbed.local/` (point DNS / `/etc/hosts` at the
Ingress IP, or change the host in the overlay).

## ArgoCD (GitOps)

ArgoCD tracks **`main` only** at the testbed overlay path. Feature branches are
built and tested by CI but never auto-deployed (no ApplicationSet / PR preview).

```bash
# Edit deploy/argocd/application.yaml: set spec.source.repoURL (and destination
# for a remote cluster), then register the Application:
kubectl apply -n argocd -f deploy/argocd/application.yaml

# Watch it:
argocd app get rack-insight        # or the ArgoCD UI
```

Healthy end state:
```
ArgoCD Application = Synced + Healthy
```

### Image flow (immutable tags)

```
main merge → CI builds & pushes  <registry>/rack-insight-*:sha-<short>
           → CI runs `kustomize edit set image` in overlays/testbed (GitOps commit)
           → ArgoCD detects the manifest change → syncs → rolling update
```

`:latest` is never used, so the running version is always identifiable
(`kubectl get deploy backend -n rack-insight -o jsonpath='{..image}'`).

## Persistent storage

Only **PostgreSQL** needs persistence (StatefulSet `volumeClaimTemplates`, 8Gi,
`ReadWriteOnce`). The backend is stateless (logs to stdout, exports stream in
memory), and Redis is an ephemeral cache — neither uses a PVC. Set
`storageClassName` in the overlay if your cluster has no default class. For a
managed/external database, point `DATABASE_URL` at it and remove the postgres
StatefulSet from the base — nothing else changes.

## Air-gapped deployment

1. On an internet-connected machine, build and export all images (backend,
   frontend, plugin, infra) with `deploy/offline/build_and_export.sh`.
2. Carry the archive in; load it into the **internal registry** (`docker load`
   then `docker tag` / `docker push` to `registry.internal:5000`).
3. Set the overlay images to the internal registry, `kubectl apply -k …` (or let
   ArgoCD sync from the internal Git mirror).

No component fetches anything from the internet at runtime.

## Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| **Pod Pending** | No schedulable node or unbound PVC. `kubectl describe pod …`; check `kubectl get pvc -n rack-insight` and set `storageClassName` in the overlay. |
| **CrashLoopBackOff (backend)** | DB not ready or bad Secret. `kubectl logs deploy/backend -n rack-insight`. The `wait-for-postgres` init container should gate this; check `DATABASE_URL` in the Secret. |
| **ImagePullBackOff** | Wrong registry/tag or missing pull secret. `kubectl describe pod …`; verify the overlay image refs and registry credentials. |
| **Readiness probe failed (backend)** | First-boot migrations still running — the startupProbe allows ~2.5 min. If it persists, check DB connectivity in the logs. |
| **Database connection failed** | `DATABASE_URL` host must be `postgres` (the Service name); confirm the postgres pod is Ready and the password matches `POSTGRES_PASSWORD`. |
| **Ingress not reachable** | Wrong `ingressClassName` or host. `kubectl get ingress -n rack-insight`; confirm the controller (`kubectl get ingressclass`) and DNS/`/etc/hosts`. |
| **ArgoCD Sync failed** | Bad `repoURL`/path or an invalid manifest. Check the ArgoCD UI diff; ensure the Secret exists (ArgoCD does not manage it). |
