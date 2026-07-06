#!/usr/bin/env bash
# Deploy the infra-dk Dokploy stack from infra/compose.yaml.
#
# Flow: render compose with /opt/infra/.env (secrets inlined) → compose.update
# (full file, BUG #3) → compose.deploy (queued). Dokploy runs
# `docker compose -p infra-dk-mebbbv up -d --pull always --remove-orphans`.
#
# Run from repo root on the VPS (needs /opt/infra/.env + VPN access to 10.99.0.1:18080).
# Env: DOKPLOY_API_KEY (or pass as arg).
set -euo pipefail

COMPOSE_ID="wev0EWTdnUoAbH-Rl0y4i"
API_KEY="${1:-${DOKPLOY_API_KEY:-}}"
ENV_FILE="/opt/infra/.env"
COMPOSE_FILE="infra/compose.yaml"
BASE="http://10.99.0.1:18080/api"

if [[ -z "$API_KEY" ]]; then
  echo "FAIL: set DOKPLOY_API_KEY or pass as arg" >&2; exit 1
fi
[[ -f "$ENV_FILE" ]]   || { echo "FAIL: $ENV_FILE missing" >&2; exit 1; }
[[ -f "$COMPOSE_FILE" ]] || { echo "FAIL: $COMPOSE_FILE missing (run from repo root)" >&2; exit 1; }

echo "Rendering compose (inline env from $ENV_FILE)..."
COMPOSE_RENDERED=$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config)

echo "compose.update (full file, composeId $COMPOSE_ID)..."
python3 - "$COMPOSE_RENDERED" "$API_KEY" "$COMPOSE_ID" "$BASE" <<'PY'
import json, os, sys, urllib.request
body = sys.argv[1]; key = sys.argv[2]; cid = sys.argv[3]; base = sys.argv[4]
payload = {"composeId": cid, "composeFile": body}
req = urllib.request.Request(f"{base}/compose.update",
    data=json.dumps(payload).encode(),
    headers={"x-api-key": key, "Content-Type": "application/json"},
    method="POST")
print(urllib.request.urlopen(req).read().decode()[:500])
PY

echo "compose.deploy..."
curl -s -X POST "$BASE/compose.deploy" -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" -d "{\"composeId\":\"$COMPOSE_ID\"}"
echo
echo "Deploy queued. Poll: curl -s $BASE/compose.one?composeId=$COMPOSE_ID -H 'x-api-key: \$KEY' | jq .status"