# Production smoke runbook

Status: read-only by default. This procedure checks the public API and authenticated
read paths without printing response bodies, credentials, signed URLs, or personal
data. It does not deploy or mutate production.

## Guardrails

- Run from an approved operator machine with network access. The default target is `https://api.skatelab.ru/v1`.
- Use a dedicated pilot smoke account whose access token is supplied by the approved secret store or process environment. Never put a password or token in a command, shell history, ticket, CI summary, or screenshot.
- Do not use `set -x`, verbose HTTP tracing, `--include`, `--dump-header`, `--fail-with-body`, or `curl -v`.
- Keep response bodies in a mode-600 temporary file only when needed for a local assertion; delete it on exit.
- A green read-only smoke does not prove video processing, sensor validity, coach validity, or release readiness. Use the pilot journey below only with explicit approval and disposable data.

## Read-only smoke

The following checks require `curl` and Python 3.11 or newer. Set
`SMOKE_ACCESS_TOKEN` out of band before running the authenticated section. The
script prints status labels and HTTP codes only.

```bash
set -euo pipefail

api_base="${SKATELAB_SMOKE_API_BASE_URL:-https://api.skatelab.ru/v1}"
api_base="${api_base%/}"
health_body="$(mktemp)"
auth_config="$(mktemp)"
trap 'rm -f "$health_body" "$auth_config"' EXIT
chmod 600 "$health_body" "$auth_config"

curl --fail --silent --show-error \
  --connect-timeout 5 --max-time 15 \
  --output "$health_body" \
  --write-out 'health_http=%{http_code}\n' \
  "$api_base/health"

python - "$health_body" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
if payload.get("status") != "ok":
    raise SystemExit("health status is not ok")
PY
printf '%s\n' 'health_status=ok'

unauth_status="$({
  curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
    --connect-timeout 5 --max-time 15 "$api_base/sessions?limit=1"
} || true)"
test "$unauth_status" = 401
printf 'unauthenticated_sessions_http=%s\n' "$unauth_status"

: "${SMOKE_ACCESS_TOKEN:?provide the smoke token through a secure environment, not this command line}"
printf 'header = "Authorization: Bearer %s"\n' "$SMOKE_ACCESS_TOKEN" > "$auth_config"

for endpoint in \
  '/sessions?limit=1' \
  '/notifications?page=1&page_size=1'; do
  label="${endpoint%%\?*}"
  status="$(curl --config "$auth_config" --fail --silent --show-error \
    --output /dev/null --write-out '%{http_code}' \
    --connect-timeout 5 --max-time 15 "$api_base$endpoint")"
  printf '%s_http=%s\n' "${label#/}" "$status"
done
```

Expected results:

- `health_http=200` and `health_status=ok`.
- `unauthenticated_sessions_http=401`.
- Authenticated `/sessions` and `/notifications` return `200`.
- Any timeout, TLS error, non-2xx authenticated response, or health status other than `ok` is a failed smoke. Do not retry mutating operations while investigating.

The temporary auth configuration contains the token and must be removed by the
trap. If the command is interrupted before cleanup, remove that file through the
approved secure process and rotate the token if exposure is possible.

## Approved pilot journey (optional)

Run this only after the read-only smoke passes and the pilot owner approves a
disposable production check:

1. Sign in to the dedicated smoke account through the normal Android or web client.
2. Create one clearly labelled disposable video session using a non-personal fixture or approved test video.
3. Confirm the upload creates one session and one process task; record only non-sensitive IDs privately.
4. Observe progress until `completed` or a known, actionable failure. On client restart, confirm the existing task ID is observed rather than queued again.
5. Confirm the result states `video-only`, `unavailable`, or `synthetic/unvalidated` honestly. Do not treat any confidence value as skating accuracy.
6. If the pilot contract includes it, verify one comment/notification and a real PDF export without saving the file in a public location.
7. Delete the disposable session, source object, derived result, notification, and any local copies through the approved product/support path. Confirm deletion before closing the smoke.

A failed optional journey is not a reason to create more test data. Preserve the
first session/task IDs in the private incident record and use
[pilot operations](pilot-operations.md).

## Evidence record

Keep evidence in the approved private release/incident system. Store status codes,
UTC timestamps, target environment, release commit or image digest, client/build
version, and a pass/fail result. Do not store tokens, passwords, signed URLs,
response bodies, emails, raw media, or IMU payloads.

```text
Date/time (UTC):
Target: production or approved non-production
Release commit/image digest:
Read-only smoke: PASS / FAIL
Optional pilot journey: PASS / FAIL / NOT RUN
HTTP codes:
Redacted operation/session/task IDs:
Failure summary and owner:
```

## Failure handling

- `health` is not `ok`: stop the pilot smoke and page the service owner; do not deploy.
- Authenticated reads fail while health is `ok`: check token expiry and auth service telemetry with the token kept private; do not request a user's password.
- Session/task state is stuck: use [pilot operations](pilot-operations.md), preserve source data, and do not enqueue a duplicate task.
- Data access, signed URL, or ownership looks wrong: treat as P0, stop pilot writes, preserve evidence, and rotate affected credentials.
