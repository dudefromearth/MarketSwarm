#!/opt/homebrew/bin/bash
set -euo pipefail
IFS=$'\n\t'

# ──────────────────────────────────────────────
# 🧠 RSS Aggregator Launcher (Local Mode)
# Author: Ernie Varitimos / FatTail Systems
# ──────────────────────────────────────────────
# Description:
#   Starts the RSS Aggregator service (rss_agg/main.py)
#   - Auto-discovers feeds.json in this directory
#   - Verifies Redis connectivity
#   - Runs setup.py to ensure schema and feeds dir ready
#   - Streams logs to local rssagg.log
#   - Auto-restarts if crashed
# ──────────────────────────────────────────────

export SERVICE_ID="rss_agg"     # ← changed from just SERVICE_ID=
export SYSTEM_REDIS_HOST="localhost"
PYTHON_BIN="${PYTHON_BIN:-python3}"

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RSSAGG_DIR="$(cd "${SCRIPT_DIR}/../../services/rss_agg" && pwd)"
LOG_DIR="${SCRIPT_DIR}"
PID_FILE="${SCRIPT_DIR}/${SERVICE_ID}.pid"
SYSTEM_REDIS_URL="redis://localhost:6379"
MAX_RESTARTS=10
RESTART_DELAY=5

# Auto-discover feeds.json
FEEDS_JSON_PATH="${SCRIPT_DIR}/feeds.json"
if [[ ! -f "$FEEDS_JSON_PATH" ]]; then
  echo "❌ Missing feeds.json at ${FEEDS_JSON_PATH}" >&2
  exit 2
fi
export FEEDS_CONFIG="$FEEDS_JSON_PATH"

log() {
  local lvl="$1"; shift
  local msg="$*"
  local t; t=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo -e "[$t][$lvl] $msg"
}

# ──────────────────────────────────────────────
# 🧩 Pre-flight checks
# ──────────────────────────────────────────────

log "INFO" "🔌 Checking Redis connectivity..."
if ! redis-cli -u "$SYSTEM_REDIS_URL" PING >/dev/null 2>&1; then
  log "ERROR" "❌ Redis unavailable at $SYSTEM_REDIS_URL"
  exit 1
fi
log "OK" "✅ Redis available."

log "INFO" "📂 Ensuring feeds directory and schemas exist..."
$PYTHON_BIN "${RSSAGG_DIR}/setup.py" || {
  log "ERROR" "❌ RSSAgg setup failed."
  exit 2
}

# ──────────────────────────────────────────────
# 🚀 Service launcher loop
# ──────────────────────────────────────────────

restart_count=0
while true; do
  restart_count=$((restart_count + 1))
  if (( restart_count > MAX_RESTARTS )); then
    log "FATAL" "💥 Max restarts reached ($MAX_RESTARTS). Exiting."
    exit 3
  fi

  log "INFO" "🚀 Starting RSS Aggregator service (attempt #${restart_count})..."
  cd "$RSSAGG_DIR"

  log "INFO" "📘 Using feeds config: ${FEEDS_CONFIG}"
  $PYTHON_BIN main.py >>"${LOG_DIR}/rssagg.log" 2>&1 &
  pid=$!
  echo "$pid" > "$PID_FILE"
  log "INFO" "🧾 PID $pid written to ${PID_FILE}"

  # Wait for process to exit
  wait $pid || true
  log "WARN" "⚠️  Service exited unexpectedly. Restarting in ${RESTART_DELAY}s..."
  sleep "$RESTART_DELAY"
done