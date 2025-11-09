#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

# ──────────────────────────────────────────────
# 🐋 Whale v3.6 — Truth-Gated Orchestrator
# Author: Ernie Varitimos / FatTail Systems
# ──────────────────────────────────────────────
# Verifies Redis health via inject-truth.sh,
# Ensures required Docker network exists,
# Then launches MarketSwarm stack cleanly.
# ──────────────────────────────────────────────

# Colors
BOLD=$(tput bold)
RESET=$(tput sgr0)
GREEN='\033[1;32m'
CYAN='\033[1;36m'
YELLOW='\033[1;33m'
RED='\033[1;31m'

NETWORK_NAME="marketswarm-bus"

show_help() {
  echo -e "${BOLD}🐋 Whale v3.6 — Truth-Gated Orchestrator${RESET}"
  echo ""
  echo -e "${CYAN}Usage:${RESET}  ./whale.sh [command]"
  echo ""
  echo -e "${CYAN}Commands:${RESET}"
  echo -e "  ${YELLOW}--verify${RESET}             Verify Redis bus health via inject-truth.sh"
  echo -e "  ${YELLOW}--up all${RESET}             Start the full MarketSwarm system"
  echo -e "  ${YELLOW}--up [service]${RESET}       Start only the specified service"
  echo -e "  ${YELLOW}--help${RESET}               Show this help message and exit"
  echo ""
  echo -e "${CYAN}Examples:${RESET}"
  echo -e "  ./whale.sh --verify"
  echo -e "  ./whale.sh --up all"
  echo -e "  ./whale.sh --up vexy_ai"
  echo ""
}

# ──────────────────────────────────────────────
# Logging helper
# ──────────────────────────────────────────────
log() {
  local lvl="$1"; shift
  local msg="$*"
  local t; t=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo -e "[$t][$lvl] $msg"
}

# ──────────────────────────────────────────────
# Ensure inject-truth.sh exists
# ──────────────────────────────────────────────
if ! [[ -x "./inject-truth.sh" ]]; then
  log "ERROR" "❌ inject-truth.sh not found or not executable."
  exit 2
fi

# ──────────────────────────────────────────────
# Command Parsing
# ──────────────────────────────────────────────
if [[ $# -eq 0 ]]; then
  echo -e "${RED}❌ No arguments provided.${RESET}"
  show_help
  exit 1
fi

MODE="$1"
TARGET_SERVICES="${2:-}"

# ──────────────────────────────────────────────
# Verify Redis via inject-truth.sh
# ──────────────────────────────────────────────
verify_redis() {
  log "INFO" "🧠 Running truth verification..."
  VERIFY_OUTPUT=$(./inject-truth.sh --verify 2>&1 || true)
  VERIFY_STATUS=$?

  echo "─────────────────────────────────────────────"
  echo "$VERIFY_OUTPUT"
  echo "─────────────────────────────────────────────"

  if [[ $VERIFY_STATUS -ne 0 ]] ||
     ! echo "$VERIFY_OUTPUT" | grep -q "✅ truth:doc verified (hash match)" ||
     ! echo "$VERIFY_OUTPUT" | grep -q "✔ 6379 healthy" ||
     ! echo "$VERIFY_OUTPUT" | grep -q "✔ 6380 healthy" ||
     ! echo "$VERIFY_OUTPUT" | grep -q "✔ 6381 healthy"; then
      log "ERROR" "❌ Redis cluster not ready — startup aborted."
      log "INFO" "Whale exiting gracefully. No containers started."
      exit 2
  fi

  log "OK" "✅ Redis verification passed. Proceeding to launch..."
}

# ──────────────────────────────────────────────
# Ensure Docker Network exists
# ──────────────────────────────────────────────
ensure_network() {
  log "INFO" "🌐 Checking for required Docker network: ${NETWORK_NAME}"
  if ! docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
    log "WARN" "⚠️  Network ${NETWORK_NAME} missing — creating..."
    if docker network create "${NETWORK_NAME}" >/dev/null 2>&1; then
      log "OK" "✅ Created network ${NETWORK_NAME}"
    else
      log "ERROR" "❌ Failed to create Docker network ${NETWORK_NAME}"
      exit 3
    fi
  else
    log "OK" "✅ Network ${NETWORK_NAME} already exists."
  fi
}

# ──────────────────────────────────────────────
# Commands
# ──────────────────────────────────────────────
case "$MODE" in
  --verify)
    verify_redis
    exit 0
    ;;
  --up)
    if [[ -z "$TARGET_SERVICES" ]]; then
      echo -e "${RED}❌ Missing service target.${RESET}"
      show_help
      exit 1
    fi

    verify_redis
    ensure_network

    if [[ "$TARGET_SERVICES" == "all" ]]; then
      docker compose up -d
    else
      docker compose up -d "$TARGET_SERVICES"
    fi

    log "OK" "✅ Stack launch complete for: $TARGET_SERVICES"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    exit 0
    ;;
  --help|-h)
    show_help
    exit 0
    ;;
  *)
    echo -e "${RED}❌ Unknown command: $MODE${RESET}"
    show_help
    exit 1
    ;;
esac