#!/opt/homebrew/bin/bash
set -euo pipefail
IFS=$'\n\t'

# ──────────────────────────────────────────────
# 🐋 Whale v3.9 — Ground-Zero Rebuild
# Author: Ernie Varitimos / FatTail Systems
# ──────────────────────────────────────────────
# This script performs a full teardown and rebuild of MarketSwarm:
#   • Verifies semantic truth + Lua
#   • Destroys ALL containers, images, volumes, and networks
#   • Rebuilds from absolute zero (no cache)
#   • Recreates the network and launches stack fresh
# ──────────────────────────────────────────────

BOLD=$(tput bold)
RESET=$(tput sgr0)
RED='\033[1;31m'
YELLOW='\033[1;33m'
CYAN='\033[1;36m'
GREEN='\033[1;32m'

NETWORK_NAME="marketswarm-bus"

log() {
  local lvl="$1"; shift
  local msg="$*"
  local t; t=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo -e "[$t][$lvl] $msg"
}

# ──────────────────────────────────────────────
# Semantic verification
# ──────────────────────────────────────────────
verify_truth() {
  log "INFO" "🧠 Running semantic truth verification..."
  VERIFY_OUTPUT=$(./inject-truth.sh --verify 2>&1 || true)
  VERIFY_STATUS=$?

  echo "─────────────────────────────────────────────"
  echo "$VERIFY_OUTPUT"
  echo "─────────────────────────────────────────────"

  if [[ $VERIFY_STATUS -ne 0 ]] ||
     ! echo "$VERIFY_OUTPUT" | grep -q "✅ truth:doc semantically consistent" ||
     ! echo "$VERIFY_OUTPUT" | grep -q "✅ Lua" ; then
      log "ERROR" "❌ Redis verification failed — aborting rebuild."
      exit 2
  fi

  log "OK" "✅ Semantic truth verified."
}

# ──────────────────────────────────────────────
# Nuclear cleanup — absolutely everything
# ──────────────────────────────────────────────
scorched_earth() {
  log "WARN" "💣 Initiating ground-zero cleanup..."
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  docker stop $(docker ps -aq) >/dev/null 2>&1 || true
  docker rm -f $(docker ps -aq) >/dev/null 2>&1 || true
  docker network prune -f >/dev/null 2>&1 || true
  docker volume prune -f >/dev/null 2>&1 || true
  docker image prune -af >/dev/null 2>&1 || true
  docker builder prune -af >/dev/null 2>&1 || true
  docker system prune -af --volumes >/dev/null 2>&1 || true
  log "OK" "🔥 Docker state wiped clean."
}

# ──────────────────────────────────────────────
# Recreate network
# ──────────────────────────────────────────────
recreate_network() {
  log "INFO" "🌐 Recreating Docker network: ${NETWORK_NAME}"
  docker network rm "${NETWORK_NAME}" >/dev/null 2>&1 || true
  docker network create "${NETWORK_NAME}" >/dev/null 2>&1
  log "OK" "✅ Fresh network ${NETWORK_NAME} created."
}

# ──────────────────────────────────────────────
# Full rebuild and launch
# ──────────────────────────────────────────────
rebuild_and_launch() {
  local target="$1"
  log "INFO" "🚧 Rebuilding Docker images from scratch..."
  if [[ "$target" == "all" ]]; then
    docker compose build --no-cache
    log "INFO" "🚀 Launching full MarketSwarm stack..."
    docker compose up -d
  else
    docker compose build --no-cache "$target"
    log "INFO" "🚀 Launching service: $target..."
    docker compose up -d "$target"
  fi
  log "OK" "✅ Stack launch complete for: $target"
  docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

# ──────────────────────────────────────────────
# Main entry
# ──────────────────────────────────────────────
if [[ $# -lt 2 && "$1" != "--verify" ]]; then
  echo -e "${RED}❌ Usage: ./whale.sh --up all | service${RESET}"
  exit 1
fi

MODE="$1"
TARGET="${2:-}"

case "$MODE" in
  --verify)
    verify_truth
    ;;
  --up)
    verify_truth
    scorched_earth
    recreate_network
    rebuild_and_launch "$TARGET"
    ;;
  *)
    echo -e "${RED}❌ Unknown command: $MODE${RESET}"
    exit 1
    ;;
esac