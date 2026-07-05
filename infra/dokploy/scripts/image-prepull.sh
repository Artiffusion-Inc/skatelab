#!/usr/bin/env bash
# Pre-pull all SkateLab images on VPS so first Dokploy deploys start instantly.
# Requires GHCR login first: echo $GHCR_PAT | docker login ghcr.io -u artiffusion-inc --password-stdin
set -euo pipefail

IMAGES=(
  "ghcr.io/artiffusion-inc/skatelab-backend:latest"
  "ghcr.io/artiffusion-inc/skatelab-frontend:latest"
  "ghcr.io/artiffusion-inc/skatelab-arq-worker:latest"
  "docker.io/prom/prometheus:v3.3.0"
)

for img in "${IMAGES[@]}"; do
  echo "Pulling: $img"
  docker pull "$img" &
done
wait

echo "All images pulled"
docker images --format "{{.Repository}}:{{.Tag}} | {{.Size}}" | grep -E "skatelab|prometheus"