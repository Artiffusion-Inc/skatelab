#!/usr/bin/env bash
# Connect a Dokploy-managed container to existing infra_app_network.
# Usage: ./network-connect.sh <container-name>
# BLOCKER #1 fix: host.docker.internal fails on Linux Docker; use docker network connect.
set -euo pipefail

CONTAINER="${1:?usage: network-connect.sh <container-name>}"
NETWORK="infra_app_network"

# Idempotent
if docker inspect "$CONTAINER" --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' 2>/dev/null | grep -q "$NETWORK"; then
  echo "Container $CONTAINER already connected to $NETWORK"
  exit 0
fi

docker network connect "$NETWORK" "$CONTAINER"
echo "Connected $CONTAINER to $NETWORK"
docker inspect "$CONTAINER" --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}={{$v.IPAddress}} {{end}}'