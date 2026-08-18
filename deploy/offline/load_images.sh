#!/usr/bin/env bash
# Load the Rack Insight image archive on an AIR-GAPPED host.
#
# Usage:
#   ./deploy/offline/load_images.sh rack-insight-images-<tag>.tar.gz
set -euo pipefail

ARCHIVE="${1:?Usage: $0 <rack-insight-images-*.tar.gz>}"

if [[ ! -f "${ARCHIVE}" ]]; then
  echo "Archive not found: ${ARCHIVE}" >&2
  exit 1
fi

echo "==> Loading images from ${ARCHIVE}"
gunzip -c "${ARCHIVE}" | docker load

echo
echo "==> Loaded images:"
docker image ls --format '{{.Repository}}:{{.Tag}}' \
  | grep -E '^(rack-insight-|postgres:17-alpine|redis:7-alpine|nginx:1.27-alpine)' || true

echo
echo "Next:"
echo "  Kubernetes (official): push images to the internal registry, then"
echo "                         kubectl apply -k deploy/kubernetes/overlays/testbed"
echo "  Local Compose (dev):   cd deploy/local && docker compose up -d"
