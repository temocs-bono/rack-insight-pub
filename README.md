# Rack Insight
ingi, temocs

**Hardware & firmware inventory and operations platform for the datacenter.**

Browse and operate HPE servers (iLO / Redfish) and Cisco switches — inventory,
firmware, network, VMs, discovery, collectors, alerts and RBAC — from one web UI,
extensible with independent plugins.

```
Browser → Ingress → Frontend (React) · Backend (FastAPI) → PostgreSQL · Redis
                                   └→ Collectors (Redfish/SSH/Virsh/Cisco) · Plugins
```

## Repository structure

Three clear buckets — **the app**, **how to deploy it**, **how to read about it**:

```
backend/            Application — FastAPI backend
frontend/           Application — React SPA
plugins/            Application — reference plugin (example-plugin)
deploy/             How to run & deploy   → see deploy/README.md
  local/              Docker Compose (local development)
  kubernetes/         Kustomize manifests (official testbed / production)
  argocd/             ArgoCD Application (GitOps)
  offline/            Air-gapped image build/export
docs/               Documentation (see the table below)
CHANGELOG.md        Release history
```

## Run it

**Local development** (Docker Compose):

```bash
cd deploy/local
docker compose -f docker-compose.yml -f docker-compose.build.yml build   # once, online
docker compose up -d
```
Open **http://localhost/** — login `admin` / `admin123!`.

**Testbed / production** runs on **Kubernetes + ArgoCD** — see
[docs/deployment.md](docs/deployment.md):

```bash
kubectl apply -k deploy/kubernetes/overlays/testbed
```

> Docker Compose is for local development only. Kubernetes is the official
> deployment path.

## Documentation

| Doc | What it covers |
| --- | --- |
| [docs/development.md](docs/development.md) | Run locally, tests, migrations, configuration, contribution flow |
| [docs/deployment.md](docs/deployment.md) | Kubernetes + ArgoCD, config reference, air-gapped, troubleshooting |
| [docs/architecture.md](docs/architecture.md) | System design, key policies, features |
| [docs/plugin-development.md](docs/plugin-development.md) | Build and deploy a plugin |
| [deploy/README.md](deploy/README.md) | Deployment folder index |
| [CHANGELOG.md](CHANGELOG.md) · [docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md) | Release history |

## Configuration

All settings are environment variables (see
[backend/.env.example](backend/.env.example)). Before any real environment set
`JWT_SECRET_KEY`, `ENCRYPTION_KEY` and `DEFAULT_ADMIN_PASSWORD`. In Kubernetes
these live in a Secret (see [docs/deployment.md](docs/deployment.md)); default
admin credentials are `admin` / `admin123!` — change them.
