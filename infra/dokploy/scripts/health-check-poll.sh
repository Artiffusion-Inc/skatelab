#!/usr/bin/env bash
# Poll health endpoints until all pass or timeout. Replaces fixed "wait 5 min" waits.
# Usage: ./health-check-poll.sh [timeout_sec] [interval_sec]
set -euo pipefail

TIMEOUT="${1:-120}"
INTERVAL="${2:-5}"
ELAPSED=0

check() {
  local name="$1" url="$2"
  local code
  code=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 5 "$url" || echo "000")
  if [[ "$code" =~ ^(200|301|302)$ ]]; then
    echo "PASS: $name ($code)"
    return 0
  fi
  echo "FAIL: $name ($code)"
  return 1
}

while [[ $ELAPSED -lt $TIMEOUT ]]; do
  echo "[${ELAPSED}s] Checking..."
  PASS=true
  check "backend /v1/health" "https://api.skatelab.ru/v1/health" || PASS=false
  check "frontend /" "https://skatelab.ru" || PASS=false
  if $PASS; then
    echo "All health checks passed"
    exit 0
  fi
  sleep $INTERVAL
  ELAPSED=$((ELAPSED + INTERVAL))
done

echo "TIMEOUT: health checks did not pass in ${TIMEOUT}s"
exit 1