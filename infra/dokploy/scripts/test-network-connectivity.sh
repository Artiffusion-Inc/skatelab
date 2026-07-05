#!/usr/bin/env bash
# Test that Caddy can reach a Dokploy container via shared infra_app_network.
# Usage: ./test-network-connectivity.sh <container-name>
set -euo pipefail

SERVICE="${1:?usage: test-network-connectivity.sh <container-name>}"
CADDY_CONTAINER="infra-caddy-1"

echo "Testing Caddy → $SERVICE connectivity..."

TARGET_IP=$(docker inspect "$SERVICE" --format '{{.NetworkSettings.Networks.infra_app_network.IPAddress}}' 2>/dev/null || true)
if [[ -z "$TARGET_IP" ]]; then
  echo "FAIL: $SERVICE not on infra_app_network"
  exit 1
fi
echo "Target IP: $TARGET_IP"

if docker exec "$CADDY_CONTAINER" sh -c "wget -q -O- http://$TARGET_IP/ 2>/dev/null | head -3" 2>/dev/null; then
  echo "PASS: Caddy can reach $SERVICE via IP"
else
  echo "FAIL: Caddy cannot reach $SERVICE via IP"
  exit 1
fi

if docker exec "$CADDY_CONTAINER" sh -c "wget -q -O- http://$SERVICE/ 2>/dev/null | head -3" 2>/dev/null; then
  echo "PASS: Caddy can resolve $SERVICE by name"
else
  echo "WARN: name resolution failed (use IP in Caddyfile)"
fi