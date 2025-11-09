#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# ──────────────────────────────────────────────
# redistrips.sh v3.0 — Antifragile Redis Bus Orchestrator
# Author: Ernie Varitimos / FatTail Systems
# ──────────────────────────────────────────────
# Manages installation, verification, version control,
# teardown, rebuild, and integration with inject-truth.sh.
# ──────────────────────────────────────────────

REDIS_PORTS=(6379 6380 6381)
BUS_NAMES=(system market intel)
CONF_DIR="/usr/local/etc/redis"
VAR_DIR="/usr/local/var"
LOG_FILE="$VAR_DIR/redistrips.log"
BREW_BIN="/opt/homebrew/bin/redis-server"
TRUTH_TOOL="/usr/local/bin/inject-truth.sh"
TARGET_VERSION="8.2.3"

log() {
  local msg="$1"; local lvl="${2:-INFO}"
  local t; t=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo -e "[$t][$lvl] $msg"
  echo "{\"time\":\"$t\",\"level\":\"$lvl\",\"msg\":\"$msg\"}" >> "$LOG_FILE"
}

ensure_redis_installed() {
  if ! command -v redis-server >/dev/null 2>&1; then
    log "🚀 Installing Redis via Homebrew..." "INFO"
    brew install redis || { log "❌ Failed to install Redis." "ERROR"; exit 1; }
  fi
}

check_version() {
  local v
  v=$(/opt/homebrew/bin/redis-server --version | awk '{print $3}' | cut -d'=' -f2)
  echo "$v"
}

upgrade_if_needed() {
  local v; v=$(check_version)
  if [[ "$v" != "$TARGET_VERSION" ]]; then
    log "🔄 Upgrading Redis ($v → $TARGET_VERSION)" "WARN"
    brew upgrade redis || true
    brew link redis --overwrite
    brew cleanup redis
  else
    log "✅ Redis already at target version $v" "OK"
  fi
}

create_config() {
  local bus="$1"; local port="$2"; local dir="$VAR_DIR/redis-$bus"
  mkdir -p "$dir"
  cat > "$CONF_DIR/$bus.conf" <<EOF
port $port
dir $dir
appendonly yes
save ""
maxmemory 2gb
maxmemory-policy allkeys-lru
logfile $VAR_DIR/redis-$bus.log
EOF
  log "🧩 Configured $bus → $CONF_DIR/$bus.conf" "INFO"
}

start_bus() {
  local bus="$1"; local port="$2"
  if lsof -i :$port >/dev/null 2>&1; then
    log "⚠️ Port $port already bound — attempting restart..." "WARN"
    stop_bus "$port"
  fi
  redis-server "$CONF_DIR/$bus.conf" --daemonize yes
  sleep 1
  redis-cli -p "$port" PING >/dev/null 2>&1 && \
    log "✅ $bus (port $port) started" "OK" || log "❌ Failed to start $bus ($port)" "ERROR"
}

stop_bus() {
  local port="$1"
  redis-cli -p "$port" SHUTDOWN NOSAVE >/dev/null 2>&1 || true
  sleep 1
}

verify_buses() {
  log "🩺 Verifying all Redis buses..." "INFO"
  for i in "${!BUS_NAMES[@]}"; do
    local bus="${BUS_NAMES[$i]}"; local port="${REDIS_PORTS[$i]}"
    if redis-cli -p "$port" PING >/dev/null 2>&1; then
      local version
      version=$(redis-cli -p "$port" INFO server | grep redis_version | cut -d: -f2 | tr -d '\r')
      log "✅ $bus → running on $port (v$version)" "OK"
    else
      log "❌ $bus → not reachable on $port" "ERROR"
    fi
  done
}

teardown_all() {
  log "🧹 Stopping all Redis instances..." "WARN"
  for p in "${REDIS_PORTS[@]}"; do
    stop_bus "$p"
  done

  log "🗑 Clearing Redis data (safe cleanup)..." "WARN"

  # Only clear redis-* data dirs under /usr/local/var, not the brew etc directory
  if ! rm -rf "$VAR_DIR"/redis-* 2>/dev/null; then
    log "⚠️  Permission denied during data cleanup — attempting recovery..." "WARN"
    sudo chown -R "$(whoami)" "$VAR_DIR"/redis-* 2>/dev/null || true
    sudo chmod -R u+rw "$VAR_DIR"/redis-* 2>/dev/null || true

    if rm -rf "$VAR_DIR"/redis-* 2>/dev/null; then
      log "✅ Data cleanup completed after permission repair." "OK"
    else
      log "❌ Data cleanup still blocked — manual removal may be required." "ERROR"
    fi
  else
    log "✅ Data cleanup completed successfully." "OK"
  fi

  # Config files may be brew-protected; remove only redis-*.conf, not the folder
  if [[ -d "$CONF_DIR" ]]; then
    for conf in "$CONF_DIR"/redis-*.conf "$CONF_DIR"/*.conf "$CONF_DIR"/system.conf "$CONF_DIR"/market.conf "$CONF_DIR"/intel.conf; do
      [[ -f "$conf" ]] || continue
      if rm -f "$conf" 2>/dev/null; then
        log "🧩 Removed config: $conf" "OK"
      else
        log "⚠️  Could not remove config (permission restricted): $conf" "WARN"
      fi
    done
  fi
}

rebuild_buses() {
  log "💥 Rebuild requested — full environment reset" "WARN"
  read -r -p "⚠️  This will stop all Redis instances and delete data. Continue? (y/N): " ans
  [[ "${ans,,}" != "y" ]] && { log "Rebuild aborted." "INFO"; exit 0; }

  teardown_all
  mkdir -p "$CONF_DIR"
  for i in "${!BUS_NAMES[@]}"; do
    create_config "${BUS_NAMES[$i]}" "${REDIS_PORTS[$i]}"
  done
  for i in "${!BUS_NAMES[@]}"; do
    start_bus "${BUS_NAMES[$i]}" "${REDIS_PORTS[$i]}"
  done
  verify_buses

  if [[ -x "$TRUTH_TOOL" ]]; then
    log "🌍 Injecting Truth post-rebuild..." "INFO"
    "$TRUTH_TOOL" --inject || log "⚠️ Truth injection failed" "WARN"
  fi
}

# ──────────────────────────────────────────────
# CLI MODES
# ──────────────────────────────────────────────
mode="${1:-start}"

case "$mode" in
  --install|install)
    ensure_redis_installed
    upgrade_if_needed
    ;;
  --start|start)
    ensure_redis_installed
    upgrade_if_needed
    mkdir -p "$CONF_DIR"
    for i in "${!BUS_NAMES[@]}"; do
      bus="${BUS_NAMES[$i]}"; port="${REDIS_PORTS[$i]}"
      [[ -f "$CONF_DIR/$bus.conf" ]] || create_config "$bus" "$port"
      start_bus "$bus" "$port"
    done
    verify_buses
    ;;
  --stop|stop)
    teardown_all
    ;;
  --verify|--status|status)
    verify_buses
    ;;
  --rebuild|rebuild)
    rebuild_buses
    ;;
  --version|version)
    log "🔢 Checking Redis versions for all buses..."
    check_bus_version() {
      local bus="$1"
      local port="$2"

      if redis-cli -p "$port" PING >/dev/null 2>&1; then
        local v
        v=$(redis-cli -p "$port" INFO server 2>/dev/null | grep '^redis_version:' | cut -d: -f2 | tr -d '\r')
        if [[ -n "$v" ]]; then
          log "✅ $bus → running on port $port (v$v)" "OK"
        else
          log "⚠️  $bus → version unavailable (responding)" "WARN"
        fi
      else
        log "❌ $bus → not reachable on port $port" "ERROR"
      fi
    }

    for i in "${!BUS_NAMES[@]}"; do
      check_bus_version "${BUS_NAMES[$i]}" "${REDIS_PORTS[$i]}"
    done
    ;;
  --help|-h)
    cat <<EOF
🧭 redistrips.sh v3.0 — Antifragile Bus Orchestrator

Usage:
  ./redistrips.sh [mode]

Modes:
  install   → Ensure Redis is installed/upgraded to $TARGET_VERSION
  start     → Start all buses (system, market, intel)
  stop      → Stop all Redis instances
  verify    → Check health and versions
  rebuild   → Full teardown + reinstall + Truth reinjection
  version   → Show active Redis versions
  help      → Show this message
EOF
    ;;
  *)
    log "❌ Unknown mode: $mode" "ERROR"
    exit 1
    ;;
esac