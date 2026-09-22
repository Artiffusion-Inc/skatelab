#!/usr/bin/env bash
# Synchronize repository-managed Traefik config to the Dokploy VPS.
#
# This is intentionally a local SSH client: the workflow checks out the exact
# commit, copies only the two source files, and the remote side installs them
# with a rollback trap before restarting the standalone dokploy-traefik container.
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../../.." && pwd)
STATIC_SOURCE="$REPO_ROOT/infra/dokploy/traefik/traefik.yml"
DYNAMIC_SOURCE="$REPO_ROOT/infra/dokploy/traefik/dynamic.yml"
REMOTE_STATIC="/etc/dokploy/traefik/traefik.yml"
REMOTE_DYNAMIC="/etc/dokploy/traefik/dynamic/skatelab.yml"
PORT=22
HOST=""
USER_NAME=""
HEALTH_URL="https://api.skatelab.ru/v1/health"
DRY_RUN=false

usage() {
  cat <<'EOF'
Usage: sync-traefik-config.sh --host HOST --user USER [options]

Options:
  --host HOST       VPS hostname or address
  --user USER       VPS SSH user
  --port PORT       SSH port (default: 22)
  --health-url URL  health endpoint (default: https://api.skatelab.ru/v1/health)
  --dry-run         validate local sources and print remote targets only
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST=${2:?missing value for --host}; shift 2 ;;
    --user) USER_NAME=${2:?missing value for --user}; shift 2 ;;
    --port) PORT=${2:?missing value for --port}; shift 2 ;;
    --health-url) HEALTH_URL=${2:?missing value for --health-url}; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -f "$STATIC_SOURCE" ]] || { echo "Missing $STATIC_SOURCE" >&2; exit 1; }
[[ -f "$DYNAMIC_SOURCE" ]] || { echo "Missing $DYNAMIC_SOURCE" >&2; exit 1; }
[[ "$PORT" =~ ^[0-9]+$ ]] || { echo "SSH port must be numeric" >&2; exit 2; }

if $DRY_RUN; then
  printf 'DRY RUN: source static=%s\n' "$STATIC_SOURCE"
  printf 'DRY RUN: source dynamic=%s\n' "$DYNAMIC_SOURCE"
  printf 'DRY RUN: remote static=%s\n' "$REMOTE_STATIC"
  printf 'DRY RUN: remote dynamic=%s\n' "$REMOTE_DYNAMIC"
  printf 'DRY RUN: health=%s\n' "$HEALTH_URL"
  exit 0
fi

[[ -n "$HOST" ]] || { echo "--host is required" >&2; exit 2; }
[[ -n "$USER_NAME" ]] || { echo "--user is required" >&2; exit 2; }
command -v ssh >/dev/null || { echo "ssh is required" >&2; exit 1; }
command -v scp >/dev/null || { echo "scp is required" >&2; exit 1; }

TARGET="$USER_NAME@$HOST"
REMOTE_TMP="/tmp/skatelab-traefik-sync-$(date +%s)-$$"
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -p "$PORT")
SCP_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -P "$PORT")

ssh "${SSH_OPTS[@]}" "$TARGET" "umask 077; mkdir -p '$REMOTE_TMP'"
scp "${SCP_OPTS[@]}" "$STATIC_SOURCE" "$DYNAMIC_SOURCE" "$TARGET:$REMOTE_TMP/"

ssh "${SSH_OPTS[@]}" "$TARGET" bash -s -- "$REMOTE_TMP" "$HEALTH_URL" <<'REMOTE'
set -euo pipefail

REMOTE_TMP=$1
HEALTH_URL=$2
REMOTE_STATIC=/etc/dokploy/traefik/traefik.yml
REMOTE_DYNAMIC=/etc/dokploy/traefik/dynamic/skatelab.yml
BACKUP_DIR="/etc/dokploy/traefik/rollback/$(date -u +%Y%m%dT%H%M%SZ)"
ROLLED_BACK=false
if [[ $(id -u) -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo -n)
fi
root_cmd() { "${SUDO[@]}" "$@"; }
docker_cmd() { root_cmd docker "$@"; }

rollback() {
  if $ROLLED_BACK; then
    return
  fi
  ROLLED_BACK=true
  if [[ -f "$BACKUP_DIR/traefik.yml" ]]; then
    root_cmd install -m 0644 "$BACKUP_DIR/traefik.yml" "$REMOTE_STATIC"
  fi
  if [[ -e "$BACKUP_DIR/skatelab.yml" ]]; then
    if [[ -e "$REMOTE_DYNAMIC" || -L "$REMOTE_DYNAMIC" ]]; then
      root_cmd rm -rf "$REMOTE_DYNAMIC"
    fi
    root_cmd cp -a "$BACKUP_DIR/skatelab.yml" "$REMOTE_DYNAMIC"
  fi
  if docker_cmd inspect dokploy-traefik >/dev/null 2>&1; then
    docker_cmd restart dokploy-traefik >/dev/null
  fi
}
trap rollback ERR

command -v docker >/dev/null || { echo "docker is required on the VPS" >&2; exit 1; }
docker_cmd inspect dokploy-traefik >/dev/null 2>&1 || {
  echo "dokploy-traefik container is missing" >&2
  exit 1
}

root_cmd install -d -m 0755 /etc/dokploy/traefik/dynamic /etc/dokploy/traefik/rollback
root_cmd install -d -m 0700 "$BACKUP_DIR"
[[ ! -e "$REMOTE_STATIC" ]] || root_cmd cp -a "$REMOTE_STATIC" "$BACKUP_DIR/traefik.yml"
if [[ -d "$REMOTE_DYNAMIC" ]]; then
  root_cmd cp -a "$REMOTE_DYNAMIC" "$BACKUP_DIR/skatelab.yml"
elif [[ -e "$REMOTE_DYNAMIC" ]]; then
  root_cmd cp -a "$REMOTE_DYNAMIC" "$BACKUP_DIR/skatelab.yml"
fi

# Validate the static config with the exact image used by the Dokploy installer.
# Traefik 3.6.7 has no check-config subcommand, so a clean startup is the check.
docker_cmd image inspect traefik:v3.6.7 >/dev/null 2>&1 || {
  echo "traefik:v3.6.7 is not present on the VPS; refusing an unvalidated install" >&2
  exit 1
}
VALIDATION_LOG="/tmp/skatelab-traefik-check-$$.log"
set +e
timeout 10s "${SUDO[@]}" docker run --rm \
  -v "$REMOTE_TMP/traefik.yml:/etc/traefik/traefik.yml:ro" \
  -v "$REMOTE_TMP/dynamic.yml:/etc/dokploy/traefik/dynamic/skatelab.yml:ro" \
  traefik:v3.6.7 \
  --configFile=/etc/traefik/traefik.yml >"$VALIDATION_LOG" 2>&1
VALIDATION_STATUS=$?
set -e
if [[ $VALIDATION_STATUS -ne 124 ]]; then
  cat "$VALIDATION_LOG" >&2
  rm -f "$VALIDATION_LOG"
  echo "Traefik config validation failed" >&2
  exit "$VALIDATION_STATUS"
fi
rm -f "$VALIDATION_LOG"

# Write both files before either becomes live, then atomically replace each target.
root_cmd install -m 0644 "$REMOTE_TMP/traefik.yml" "$REMOTE_STATIC.new"
if [[ -d "$REMOTE_DYNAMIC" ]]; then
  root_cmd rm -rf "$REMOTE_DYNAMIC"
fi
root_cmd install -m 0644 "$REMOTE_TMP/dynamic.yml" "$REMOTE_DYNAMIC.new"
root_cmd mv -f "$REMOTE_STATIC.new" "$REMOTE_STATIC"
root_cmd mv -f "$REMOTE_DYNAMIC.new" "$REMOTE_DYNAMIC"

docker_cmd restart dokploy-traefik >/dev/null
curl --fail --silent --show-error --retry 12 --retry-delay 5 --retry-connrefused \
  --max-time 10 "$HEALTH_URL" >/dev/null

trap - ERR
rm -rf "$REMOTE_TMP"
echo "Traefik config synchronized; backup: $BACKUP_DIR"
REMOTE
