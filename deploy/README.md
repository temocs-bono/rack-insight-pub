# Deploy

Everything about **running and deploying** Rack Insight lives here. The
application source is elsewhere (`../backend`, `../frontend`, `../plugins`).

| Folder | What it is | When to use it |
| --- | --- | --- |
| [`local/`](local/) | Docker Compose stack | **Local development** — fast inner loop on one machine |
| [`kubernetes/`](kubernetes/) | Kustomize manifests (`base` + `overlays/`) | **Official testbed / production** runtime |
| [`argocd/`](argocd/) | ArgoCD `Application` | **GitOps** delivery (ArgoCD tracks `main`) |
| [`offline/`](offline/) | Image build/export + load scripts | **Air-gapped** transfer of the container images |

## TL;DR

```bash
# Local development (Docker Compose)
cd deploy/local
docker compose -f docker-compose.yml -f docker-compose.build.yml build   # once, online
docker compose up -d                                                     # http://localhost/

# Kubernetes testbed (Kustomize)
kubectl apply -n rack-insight -f deploy/kubernetes/base/secrets/secret.example.yaml   # edit first!
kubectl apply -k deploy/kubernetes/overlays/testbed

# GitOps (ArgoCD)
kubectl apply -n argocd -f deploy/argocd/application.yaml
```

Full guide: [`../docs/deployment.md`](../docs/deployment.md).
