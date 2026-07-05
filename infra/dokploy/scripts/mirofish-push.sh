#!/usr/bin/env bash
# Push localhost/mirofish-local:latest to GHCR.
# BLOCKER finding #28: Dokploy doesn't support pull_policy: never / local-only images.
# Must exist in a registry. Run on VPS where the local image lives.
set -euo pipefail

GHCR_IMAGE="ghcr.io/artiffusion-inc/mirofish-local:latest"

if ! docker image inspect localhost/mirofish-local:latest >/dev/null 2>&1; then
  echo "localhost/mirofish-local:latest not found. Build it first (see /opt/infra compose mirofish build)."
  exit 1
fi

echo "Tagging + pushing $GHCR_IMAGE"
docker tag localhost/mirofish-local:latest "$GHCR_IMAGE"
docker push "$GHCR_IMAGE"
echo "Pushed: $GHCR_IMAGE"