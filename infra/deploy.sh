#!/usr/bin/env bash
# SkateLab deploy script — runs on VPS
# Triggered by GitHub Actions after build+push to GHCR
set -euo pipefail

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
/usr/bin/docker compose pull backend frontend

# Restart app services
/usr/bin/docker compose up -d --remove-orphans

# Update Caddy config (zero-downtime reload, restart as fallback)
cp /opt/skatelab/Caddyfile /opt/infra/services/caddy/Caddyfile
/usr/bin/docker exec infra-caddy-1 caddy reload --config /etc/caddy/Caddyfile 2>/dev/null \
  || /usr/bin/docker restart infra-caddy-1

# Wait for backend startup
sleep 10

# Database migrations
/usr/bin/docker exec skatelab-backend-1 alembic upgrade head

# Health check (2min timeout)
timeout 120 bash -c 'while true; do /usr/bin/docker exec skatelab-backend-1 python -c "import urllib.request; urllib.request.urlopen(\"http://127.0.0.1:8000/api/v1/health\", timeout=2)" 2>/dev/null && echo "Backend healthy" && exit 0; sleep 10; done'

# Cleanup old images
/usr/bin/docker image prune -f --filter "until=24h" || true
