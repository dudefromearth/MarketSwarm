#!/usr/bin/env bash
set -euo pipefail
svc="${1:-}"
[[ -z "$svc" ]] && { echo "Usage: scripts/rebuild.sh <service>"; exit 1; }

docker compose rm -sf "$svc" || true
docker builder prune -f
docker compose build --no-cache --pull "$svc"
docker compose up -d --force-recreate --no-deps "$svc"
docker compose logs -f "$svc"