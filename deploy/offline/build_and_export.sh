#!/usr/bin/env bash
# Build all Rack Insight images on an INTERNET-CONNECTED machine and export them
# (plus the infrastructure images) into archives that can be carried into an
# air-gapped network. The same images run under Kubernetes (load them into the
# internal registry) and under local Docker Compose.
#
# Usage:
#   ./deploy/offline/build_and_export.sh [IMAGE_TAG]
#
# Output (in ./dist):
#   rack-insight-images-<tag>.tar.gz   (all docker images)
#   rack-insight-deploy-<tag>.tar.gz   (compose + k8s manifests + configs)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE_TAG="${1:-${IMAGE_TAG:-1.4.0}}"
IMAGE_PREFIX="${IMAGE_PREFIX:-rack-insight}"
DIST_DIR="${REPO_ROOT}/dist"

BACKEND_IMAGE="${IMAGE_PREFIX}-backend:${IMAGE_TAG}"
FRONTEND_IMAGE="${IMAGE_PREFIX}-frontend:${IMAGE_TAG}"
# Bundled plugin images (add new plugins here to ship them in the air-gap bundle).
PLUGIN_IMAGES=(
  "${IMAGE_PREFIX}-plugin-example:${IMAGE_TAG}"
)
INFRA_IMAGES=(
  "postgres:17-alpine"
  "redis:7-alpine"
  "nginx:1.27-alpine"
)

mkdir -p "${DIST_DIR}"

echo "==> Building application images (tag: ${IMAGE_TAG})"
docker build -t "${BACKEND_IMAGE}" "${REPO_ROOT}/backend"
docker build -t "${FRONTEND_IMAGE}" "${REPO_ROOT}/frontend"

echo "==> Building plugin images"
docker build -t "${IMAGE_PREFIX}-plugin-example:${IMAGE_TAG}" "${REPO_ROOT}/plugins/example-plugin"

echo "==> Pulling infrastructure images"
for image in "${INFRA_IMAGES[@]}"; do
  docker pull "${image}"
done

IMAGES_ARCHIVE="${DIST_DIR}/rack-insight-images-${IMAGE_TAG}.tar.gz"
echo "==> Exporting images to ${IMAGES_ARCHIVE}"
docker save "${BACKEND_IMAGE}" "${FRONTEND_IMAGE}" "${PLUGIN_IMAGES[@]}" "${INFRA_IMAGES[@]}" \
  | gzip > "${IMAGES_ARCHIVE}"

DEPLOY_ARCHIVE="${DIST_DIR}/rack-insight-deploy-${IMAGE_TAG}.tar.gz"
echo "==> Packaging deploy bundle to ${DEPLOY_ARCHIVE}"
tar -czf "${DEPLOY_ARCHIVE}" -C "${REPO_ROOT}" \
  deploy/local \
  deploy/kubernetes \
  deploy/argocd \
  deploy/offline/load_images.sh \
  backend/.env.example \
  README.md

echo
echo "Done. Copy these two files into the air-gapped network:"
ls -lh "${IMAGES_ARCHIVE}" "${DEPLOY_ARCHIVE}"
echo
echo "On the air-gapped host:"
echo "  tar -xzf rack-insight-deploy-${IMAGE_TAG}.tar.gz"
echo "  ./deploy/offline/load_images.sh rack-insight-images-${IMAGE_TAG}.tar.gz"
echo "  # Kubernetes (official): load images into the internal registry, then"
echo "  #   kubectl apply -k deploy/kubernetes/overlays/testbed"
echo "  # Local Compose:  cd deploy/local && IMAGE_TAG=${IMAGE_TAG} docker compose up -d"
