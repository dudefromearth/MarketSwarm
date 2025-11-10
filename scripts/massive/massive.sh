#!/opt/homebrew/bin/bash
set -euo pipefail
IFS=$'\n\t'

# ──────────────────────────────────────────────
# 💹 Massive Service Launcher
# Author: Ernie Varitimos / FatTail Systems
# ──────────────────────────────────────────────
# Starts the Massive data ingestion service.
# Publishes to Market Redis and reports to System Redis.
# Self-heals on crash.
# ──────────────────────────────────────────────

SERVICE_ID="massive"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SERVICE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../massive" && pwd)"
LOG_DIR="${SERVICE_DIR}/../logs/services/${SERVICE_ID}"
PID_FILE="${SERVICE_DIR}/../${SERVICE_ID}.pid"

SYSTEM_REDIS_URL="redis://localhost:6379"
MARKET_REDIS_URL="redis://localhost:6380"

MAX_RESTARTS=10
RESTART_DELAY=5

mkdir -p "$LOG_DIR"

log() {
  local lvl="$1"; shift
  local msg="$*"
  local t; t=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo -e "[$t][$lvl] $msg"
}

# ──────────────────────────────────────────────
# 🔍 Pre-flight checks
# ──────────────────────────────────────────────
log "INFO" "🔌 Checking Redis connectivity..."
if ! redis-cli -u "$SYSTEM_REDIS_URL" PING >/dev/null 2>&1; then
  log "ERROR" "❌ System Redis unavailable at $SYSTEM_REDIS_URL"
  exit 1
fi
if ! redis-cli -u "$MARKET_REDIS_URL" PING >/dev/null 2>&1; then
  log "ERROR" "❌ Market Redis unavailable at $MARKET_REDIS_URL"
  exit 1
fi
log "OK" "✅ Redis buses available."

# ──────────────────────────────────────────────
# 🌎 Environment Variables
# ──────────────────────────────────────────────
export SERVICE_ID="massive"
export SYSTEM_REDIS_URL="$SYSTEM_REDIS_URL"
export MARKET_REDIS_URL="$MARKET_REDIS_URL"
export POLYGON_API_KEY="${POLYGON_API_KEY:-YOUR_KEY_HERE}"
export MODE="${MODE:-chainfeed}"
export GROUP="${GROUP:-SPX}"
export HB_INTERVAL_SEC="${HB_INTERVAL_SEC:-5}"

# ──────────────────────────────────────────────
# 🚀 Launch Loop
# ──────────────────────────────────────────────
restart_count=0
while true; do
  restart_count=$((restart_count + 1))
  if (( restart_count > MAX_RESTARTS )); then
    log "FATAL" "💥 Max restarts reached ($MAX_RESTARTS). Exiting."
    exit 3
  fi

  log "INFO" "🚀 Starting Massive service (attempt #${restart_count})..."
  cd "$SERVICE_DIR"

  # Run Massive main.py
  $PYTHON_BIN main.py >>"$LOG_DIR/massive.log" 2>&1 &
  pid=$!
  echo "$pid" > "$PID_FILE"
  log "INFO" "🧾 PID $pid written to ${PID_FILE}"

  wait $pid || true
  log "WARN" "⚠️  Massive exited unexpectedly. Restarting in ${RESTART_DELAY}s..."
  sleep "$RESTART_DELAY"
done