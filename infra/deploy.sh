#!/usr/bin/env bash
# SkateLab deploy script — runs on VPS
# Triggered by GitHub Actions after build+push to GHCR
set -euo pipefail

echo "Deploy running as: $(id) ($(whoami))"

cd /opt/skatelab

# Load secrets
set -a
source .env
set +a

# Ensure shared network
/usr/bin/docker network create infra_app_network 2>/dev/null || true

# GHCR auth
echo "$GHCR_PAT" | /usr/bin/docker login ghcr.io -u "$GHCR_OWNER" --password-stdin

# Use prod compose file
cp /opt/skatelab/compose.prod.yaml /opt/skatelab/compose.yaml

# Pull new images
/usr/bin/docker compose pull backend frontend worker-heavy worker-fast
# worker-* use skatelab-arq-worker image (compose maps service→image); pull by service name

# Zero-downtime rollout for app services
/usr/bin/docker rollout --timeout 60 backend
/usr/bin/docker rollout --timeout 30 frontend

# arq workers have no HTTP healthcheck — recreate directly (jobs persist in Valkey,
# a restart just reconnects to the queue). Use --no-deps so worker startup never
# blocks on backend/frontend health.
/usr/bin/docker compose up -d --no-deps worker-heavy worker-fast

# Update non-rollout services (prometheus etc)
/usr/bin/docker compose up -d --remove-orphans --no-deps prometheus

# Update Caddy config (zero-downtime reload, restart as fallback)
cp /opt/skatelab/Caddyfile /opt/infra/services/caddy/Caddyfile
/usr/bin/docker exec infra-caddy-1 caddy reload --config /etc/caddy/Caddyfile 2>/dev/null \
  || /usr/bin/docker restart infra-caddy-1

# Database migrations (run after rollout — new container has latest code)
BACKEND=$(/usr/bin/docker ps --filter "label=com.docker.compose.service=backend" --format "{{.Names}}" | head -1)
if ! /usr/bin/docker exec "$BACKEND" alembic upgrade head; then
  echo "::error::Alembic migration failed — rolling back backend"
  /usr/bin/docker rollout --timeout 60 --rollback backend
  exit 1
fi

# Health check (2min timeout)
timeout 120 bash -c "while true; do /usr/bin/docker exec $BACKEND python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=2)\" 2>/dev/null && echo 'Backend healthy' && exit 0; sleep 10; done"

# Cleanup old images
/usr/bin/docker image prune -f --filter "until=24h" || true