#!/opt/homebrew/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# RSS Aggregator Launcher (Host-Native)
# Service: rss_agg  |  Author: Ernie Varitimos / FatTail Systems
# Purpose:
#   - Supervise the Python service (services/rss_agg/main.py)
#   - Preflight checks (Redis + feeds.json + setup.py)
#   - Structured logs, PID + PGID tracking
#   - Clean shutdown: kills entire process group (child + grandchildren)
#   - Admin UX: help, status, stop, tail, env, doctor
#
# Commands:
#   ./rssagg.sh start      Start supervising the Python service (default)
#   ./rssagg.sh once       Run once (no restarts), then exit with child's code
#   ./rssagg.sh stop       Stop everything this launcher spawned and the launcher
#   ./rssagg.sh status     Show PIDs/PGIDs and the resolved command
#   ./rssagg.sh tail       Follow the service log
#   ./rssagg.sh env        Print resolved paths, vars, and derived values
#   ./rssagg.sh doctor     Run preflight checks (Redis, feeds.json, dirs)
#   ./rssagg.sh help|-h    Show full help
#   ./rssagg.sh --version  Print script version
#
# Environment variables (optional):
#   SERVICE_ID            Service label (default: rss_agg)
#   PYTHON_BIN            Python interpreter (default: python3)
#   SYSTEM_REDIS_HOST     Redis host (default: localhost)
#   SYSTEM_REDIS_PORT     Redis port (default: 6379)
#   SYSTEM_REDIS_URL      Full URL (default: redis://localhost:6379)
#   FEEDS_CONFIG          Path to feeds.json (auto: <script_dir>/feeds.json)
#   MAX_RESTARTS          Max automatic restarts (default: 10)
#   RESTART_DELAY         Seconds between restarts (default: 5)
#
# Files/dirs (relative to this script unless overridden):
#   scripts/rssagg/rssagg.sh        ← this launcher
#   services/rss_agg/main.py        ← service entry point
#   services/rss_agg/setup.py       ← bootstrap schema/dirs
#   scripts/rssagg/run/*.pid        ← PID/PGID/launcher pid files
#   scripts/rssagg/rssagg.log       ← service log
#
# Examples:
#   ./rssagg.sh start
#   ./rssagg.sh once
#   ./rssagg.sh status
#   ./rssagg.sh tail
#   ./rssagg.sh stop
#
# Exit codes:
#   0 success | 1 redis unavailable | 2 config missing | 3 max restarts
#
# Notes:
#   - The Python process is labeled in ps/top as "rss_agg:main".
#   - Stopping kills the entire process group (no orphaned children).
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail
IFS=$'\n\t'

VERSION="1.3.0"

# ── Config & Paths ───────────────────────────────────────────────────────────
SERVICE_ID="${SERVICE_ID:-rss_agg}"
PROC_TITLE="${PROC_TITLE:-${SERVICE_ID}:main}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

SYSTEM_REDIS_HOST="${SYSTEM_REDIS_HOST:-localhost}"
SYSTEM_REDIS_PORT="${SYSTEM_REDIS_PORT:-6379}"
SYSTEM_REDIS_URL="${SYSTEM_REDIS_URL:-redis://${SYSTEM_REDIS_HOST}:${SYSTEM_REDIS_PORT}}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment overrides if .env exists
ENV_FILE="${SCRIPT_DIR}/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -o allexport
  source "$ENV_FILE"
  set +o allexport
fi

ROOT_DIR="$(cd "${SCRIPT_DIR}/../../" && pwd)"
RSSAGG_DIR="$(cd "${ROOT_DIR}/services/rss_agg" && pwd)"
RUN_DIR="${SCRIPT_DIR}/run";  mkdir -p "$RUN_DIR"
LOG_DIR="${SCRIPT_DIR}";      mkdir -p "$LOG_DIR"

PID_FILE="${RUN_DIR}/${SERVICE_ID}.pid"                # child PID (python)
PGID_FILE="${RUN_DIR}/${SERVICE_ID}.pgid"              # child's process group
LAUNCHER_PID_FILE="${RUN_DIR}/${SERVICE_ID}.launcher.pid"
LOG_FILE="${LOG_DIR}/rssagg.log"

FEEDS_CONFIG="${FEEDS_CONFIG:-${SCRIPT_DIR}/feeds.json}"
export SERVICE_ID SYSTEM_REDIS_HOST SYSTEM_REDIS_PORT FEEDS_CONFIG

MAX_RESTARTS="${MAX_RESTARTS:-10}"
RESTART_DELAY="${RESTART_DELAY:-5}"

# ── Logging ──────────────────────────────────────────────────────────────────
log() {
  local lvl="$1"; shift
  local t; t=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo "[$t][$lvl] $*"
}

# ── Help / Usage ─────────────────────────────────────────────────────────────
usage() {
  cat <<'HELP'
RSS Aggregator Launcher – help

Usage:
  rssagg.sh [command]

Commands:
  start        Start supervising the Python service (default)
  once         Run once (no restarts), then exit with child's code
  stop         Stop the entire process group and the launcher
  status       Show PIDs/PGIDs and the command/args of child
  tail         Follow the service log (rssagg.log)
  env          Print resolved configuration and file paths
  doctor       Preflight: Redis ping, feeds.json presence, setup.py
  help|-h      Show this help text
  --version    Print script version

Environment (override as needed):
  SERVICE_ID, PYTHON_BIN, SYSTEM_REDIS_HOST, SYSTEM_REDIS_PORT,
  SYSTEM_REDIS_URL, FEEDS_CONFIG, MAX_RESTARTS, RESTART_DELAY

Examples:
  ./rssagg.sh start
  ./rssagg.sh once
  ./rssagg.sh status
  ./rssagg.sh tail
  FEEDS_CONFIG=/path/to/feeds.json ./rssagg.sh start

Exit codes:
  0 OK | 1 Redis unavailable | 2 config missing | 3 max restarts reached
HELP
}

# ── Utilities ────────────────────────────────────────────────────────────────
print_env() {
  cat <<ENV
Resolved environment and paths:
  VERSION            = ${VERSION}
  SERVICE_ID         = ${SERVICE_ID}
  PROC_TITLE         = ${PROC_TITLE}
  PYTHON_BIN         = $(command -v "${PYTHON_BIN}" 2>/dev/null || echo "<not found>")
  SYSTEM_REDIS_HOST  = ${SYSTEM_REDIS_HOST}
  SYSTEM_REDIS_PORT  = ${SYSTEM_REDIS_PORT}
  SYSTEM_REDIS_URL   = ${SYSTEM_REDIS_URL}
  FEEDS_CONFIG       = ${FEEDS_CONFIG}
  ROOT_DIR           = ${ROOT_DIR}
  RSSAGG_DIR         = ${RSSAGG_DIR}
  SCRIPT_DIR         = ${SCRIPT_DIR}
  RUN_DIR            = ${RUN_DIR}
  LOG_FILE           = ${LOG_FILE}
  PID_FILE           = ${PID_FILE}
  PGID_FILE          = ${PGID_FILE}
  LAUNCHER_PID_FILE  = ${LAUNCHER_PID_FILE}
  MAX_RESTARTS       = ${MAX_RESTARTS}
  RESTART_DELAY      = ${RESTART_DELAY}
ENV
}

doctor() {
  local ok=0
  [[ -f "$FEEDS_CONFIG" ]] || { log ERROR "feeds.json missing at $FEEDS_CONFIG"; ok=2; }
  command -v redis-cli >/dev/null 2>&1 || { log ERROR "redis-cli not found in PATH"; ok=2; }
  if ! redis-cli -u "$SYSTEM_REDIS_URL" PING >/dev/null 2>&1; then
    log ERROR "Redis unavailable at $SYSTEM_REDIS_URL"; [[ $ok -eq 0 ]] && ok=1
  else
    log OK "Redis reachable at $SYSTEM_REDIS_URL"
  fi
  if ! "${PYTHON_BIN}" -c 'import sys; sys.exit(0)' >/dev/null 2>&1; then
    log ERROR "Python not found or not runnable: ${PYTHON_BIN}"; ok=2
  else
    log OK "Python resolved: $(command -v "${PYTHON_BIN}")"
  fi
  if [[ -f "${RSSAGG_DIR}/setup.py" ]]; then
    log INFO "Running setup.py…"
    "${PYTHON_BIN}" "${RSSAGG_DIR}/setup.py" || { log ERROR "setup.py failed"; ok=2; }
  else
    log ERROR "Missing ${RSSAGG_DIR}/setup.py"; ok=2
  fi
  return "$ok"
}

# ── Runtime control ──────────────────────────────────────────────────────────
cleanup_group() {
  # Kill entire process group if we have its PGID; else fall back to PID.
  if [[ -f "$PGID_FILE" ]]; then
    local pgid; pgid=$(tr -d '[:space:]' < "$PGID_FILE")
    log INFO "Stopping process group PGID=$pgid"
    kill -TERM "-$pgid" 2>/dev/null || true
    for _ in {1..20}; do sleep 0.25; pgrep -g "$pgid" >/dev/null || break; done
    kill -KILL "-$pgid" 2>/dev/null || true
  fi
  if [[ -f "$PID_FILE" ]]; then
    local cpid; cpid=$(cat "$PID_FILE")
    log INFO "Stopping child PID=$cpid"
    kill -TERM "$cpid" 2>/dev/null || true
    sleep 1
    kill -KILL "$cpid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE" "$PGID_FILE" "$LAUNCHER_PID_FILE"
}

preflight() {
  [[ -f "$FEEDS_CONFIG" ]] || { log ERROR "❌ Missing feeds.json at ${FEEDS_CONFIG}"; exit 2; }
  if ! redis-cli -u "$SYSTEM_REDIS_URL" PING >/dev/null 2>&1; then
    log ERROR "❌ Redis unavailable at $SYSTEM_REDIS_URL"; exit 1
  fi
  log OK "✅ Redis available."
  log INFO "📂 Ensuring feeds directory and schemas exist…"
  "${PYTHON_BIN}" "${RSSAGG_DIR}/setup.py" || { log ERROR "❌ RSSAgg setup failed."; exit 2; }
}

start() {
  # Prevent double-run if PID still live
  if [[ -f "$PID_FILE" ]] && ps -p "$(cat "$PID_FILE")" >/dev/null 2>&1; then
    log WARN "Already running (pid $(cat "$PID_FILE")). Use: $0 status|stop"
    exit 0
  fi

  echo $$ > "$LAUNCHER_PID_FILE"
  log INFO "launcher_pid=$$, python_bin=$(command -v "$PYTHON_BIN"), rssagg_dir=$RSSAGG_DIR"

  preflight

  local restart_count=0 stop_requested=0
  on_signal() { stop_requested=1; cleanup_group; log OK "Stopped by signal"; exit 0; }
  trap on_signal INT TERM HUP QUIT

  while (( restart_count < MAX_RESTARTS )); do
    ((restart_count++))
    log INFO "🚀 Starting RSS Aggregator (attempt #$restart_count)…"
    cd "$RSSAGG_DIR"

    # Spawn python with a friendly ps title in a subshell so exec -a doesn't replace this launcher
    ( exec -a "$PROC_TITLE" "$PYTHON_BIN" main.py >>"$LOG_FILE" 2>&1 ) &
    local pid=$!
    echo "$pid" > "$PID_FILE"

    # Record the child's process group (covers grandchildren)
    local pgid
    pgid=$(ps -o pgid= -p "$pid" | tr -d '[:space:]')
    [[ -n "$pgid" ]] && echo "$pgid" > "$PGID_FILE"

    log INFO "🧾 child_pid=$pid pgid=$pgid log=$LOG_FILE"
    set +e; wait "$pid"; exit_code=$?; set -e

    [[ $stop_requested -eq 1 ]] && { cleanup_group; exit 0; }
    log WARN "⚠️  Child exited (code=$exit_code). Restarting in ${RESTART_DELAY}s…"
    sleep "$RESTART_DELAY"
  done

  log FATAL "💥 Max restarts reached ($MAX_RESTARTS). Exiting."
  exit 3
}

once() {
  # Prevent double-run if PID still live
  if [[ -f "$PID_FILE" ]] && ps -p "$(cat "$PID_FILE")" >/dev/null 2>&1; then
    log WARN "Already running (pid $(cat "$PID_FILE")). Use: $0 status|stop"
    exit 0
  fi

  echo $$ > "$LAUNCHER_PID_FILE"
  log INFO "launcher_pid=$$, mode=once, python_bin=$(command -v "$PYTHON_BIN"), rssagg_dir=$RSSAGG_DIR"

  preflight

  cd "$RSSAGG_DIR"
  ( exec -a "$PROC_TITLE" "$PYTHON_BIN" main.py >>"$LOG_FILE" 2>&1 ) &
  local pid=$!
  echo "$pid" > "$PID_FILE"

  local pgid
  pgid=$(ps -o pgid= -p "$pid" | tr -d '[:space:]')
  [[ -n "$pgid" ]] && echo "$pgid" > "$PGID_FILE"

  log INFO "🧾 child_pid=$pid pgid=$pgid log=$LOG_FILE"
  set +e; wait "$pid"; local exit_code=$?; set -e
  cleanup_group
  exit "$exit_code"
}

stop() {
  # Tell the running launcher loop to exit so it won't respawn the child
  if [[ -f "$LAUNCHER_PID_FILE" ]]; then
    local lpid; lpid=$(cat "$LAUNCHER_PID_FILE")
    if ps -p "$lpid" >/dev/null 2>&1; then
      log INFO "Signaling launcher PID=$lpid"
      kill -TERM "$lpid" 2>/dev/null || true
      # brief wait for the launcher to clean up its group
      for _ in {1..20}; do sleep 0.1; ps -p "$lpid" >/dev/null 2>&1 || break; done
    else
      log WARN "Stale launcher PID file found (PID=$lpid not running)"
    fi
  else
    log WARN "No launcher PID file; proceeding with child/group cleanup"
  fi
  cleanup_group
  log OK "Stopped"
}

status() {
  if [[ -f "$PID_FILE" ]]; then
    local pid; pid=$(cat "$PID_FILE")
    log INFO "Child: $(ps -o pid,ppid,pgid,comm,args -p "$pid" | tail -n +2)"
  else
    log WARN "No child PID file"
  fi
  if [[ -f "$LAUNCHER_PID_FILE" ]]; then
    local lpid; lpid=$(cat "$LAUNCHER_PID_FILE")
    log INFO "Launcher: $(ps -o pid,ppid,pgid,comm,args -p "$lpid" | tail -n +2 || true)"
  else
    log WARN "No launcher PID file"
  fi
  if [[ -f "$PGID_FILE" ]]; then
    local pgid; pgid=$(tr -d '[:space:]' < "$PGID_FILE")
    if pgrep -a -g "$pgid" >/dev/null 2>&1; then
      log INFO "Process group contains: $(pgrep -a -g "$pgid" | tr '\n' ' ' )"
    else
      # Fallback for systems missing pgrep -g: list via ps/awk
      local grp; grp=$(ps -axo pid,pgid,comm,args | awk -v G="$pgid" '$2==G {print $0}')
      if [[ -n "${grp:-}" ]]; then
        log INFO "Process group members:\n$grp"
      else
        log INFO "Process group: <empty>"
      fi
    fi
  fi
  log INFO "Log file: $LOG_FILE"
}

tail_logs() { exec tail -F "$LOG_FILE"; }

# ── Entrypoint ───────────────────────────────────────────────────────────────
cmd="${1:-start}"
case "$cmd" in
  start) start ;;
  once)  once ;;
  stop)  stop ;;
  status) status ;;
  tail) tail_logs ;;
  env)  print_env ;;
  doctor) doctor; exit $? ;;
  help|-h) usage; exit 0 ;;
  --version) echo "rssagg.sh version ${VERSION}"; exit 0 ;;
  *) usage; exit 2 ;;
esac
