#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# ──────────────────────────────────────────────
# inject-truth.sh v3.0 — Antifragile + Rebuild
# Author: Ernie Varitimos / FatTail Systems
# ──────────────────────────────────────────────

DEFAULT_TRUTH="truth.json"
LOG_FILE="/usr/local/var/log/inject-truth.log"
REDIS_PORTS=(6379 6380 6381)
MAX_RETRIES=5
RETRY_DELAY=1

# ──────────────────────────────────────────────
log() {
  local msg="$1"; local level="${2:-INFO}"
  local t; t=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo -e "[$t][$level] $msg"
  echo "{\"time\":\"$t\",\"level\":\"$level\",\"msg\":\"$msg\"}" >>"$LOG_FILE"
}

sha256sum_mac() { shasum -a 256 "$1" | awk '{print $1}'; }

wait_for_port() {
  local port="$1"; local i=0
  until redis-cli -p "$port" PING >/dev/null 2>&1; do
    ((i++))
    ((i>MAX_RETRIES)) && { log "Port $port unresponsive." "ERROR"; return 1; }
    log "Waiting for Redis on $port..." "WARN"; sleep "$RETRY_DELAY"
  done
}

inject_truth() {
  local port="$1" f="$2"
  local json hash; json=$(cat "$f"); hash=$(sha256sum_mac "$f")
  log "Injecting truth → port $port" "INFO"
  if redis-cli -p "$port" -x SET truth:doc <<<"$json" >/dev/null; then
    redis-cli -p "$port" SET truth:hash "$hash" >/dev/null
    redis-cli -p "$port" SET truth:last_injected "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" >/dev/null
    log "✅ Injected OK on $port (hash=$hash)" "OK"
  else log "❌ Injection failed on $port" "ERROR"; fi
}

verify_truth() {
  local port="$1" f="$2"
  local local_hash live_hash
  local_hash=$(sha256sum_mac "$f")
  live_hash=$(redis-cli -p "$port" GET truth:hash 2>/dev/null || echo "none")
  if [[ "$local_hash" == "$live_hash" ]]; then
    log "✅ truth:doc verified (hash match) on $port" "OK"
  else
    log "⚠️ Hash drift on $port → reinject" "WARN"; inject_truth "$port" "$f"
  fi
}

diagnose_truth() {
  local port="$1"
  log "🩺 Diagnosing port $port" "INFO"
  if ! redis-cli -p "$port" PING >/dev/null 2>&1; then log "❌ Offline $port" "ERROR"; return; fi
  local keys; keys=$(redis-cli -p "$port" KEYS "truth:*" | wc -l | tr -d ' ')
  log "Found $keys truth keys" "INFO"
  local live local_hash; live=$(redis-cli -p "$port" GET truth:hash 2>/dev/null||echo none)
  local_hash=$(sha256sum_mac "$DEFAULT_TRUTH")
  [[ "$live" == "$local_hash" ]] && log "✅ Hash OK ($live)" "OK" || log "⚠️ Hash mismatch" "WARN"
}

self_heal() {
  log "🧠 Self-heal starting..." "INFO"
  for p in "${REDIS_PORTS[@]}"; do
    if ! redis-cli -p "$p" PING >/dev/null 2>&1; then
      log "🧯 Restarting Redis $p..." "WARN"
      redis-server --port "$p" --daemonize yes || log "❌ Restart fail $p" "ERROR"
      wait_for_port "$p" || continue
    fi; verify_truth "$p" "$DEFAULT_TRUTH"
  done
}

rebuild_environment() {
  log "💥 REBUILD requested — full teardown and reinstall" "WARN"
  read -r -p "⚠️  This will stop all Redis instances and delete data. Continue? (y/N): " ans
  [[ "${ans,,}" != "y" ]] && { log "Rebuild aborted." "INFO"; exit 0; }

  for p in "${REDIS_PORTS[@]}"; do
    log "🛑 Stopping Redis on $p" "INFO"
    redis-cli -p "$p" SHUTDOWN NOSAVE >/dev/null 2>&1 || true
    sleep 1
  done

  sudo mkdir -p /usr/local/etc/redis /usr/local/var
  for bus in system market intel; do
    local port
    case "$bus" in
      system) port=6379;;
      market) port=6380;;
      intel)  port=6381;;
    esac
    local dir="/usr/local/var/redis-$bus"
    log "♻️ Recreating $dir" "INFO"
    sudo rm -rf "$dir"
    sudo mkdir -p "$dir"
    sudo tee "/usr/local/etc/redis/$bus.conf" >/dev/null <<EOF
port $port
dir $dir
appendonly yes
appendfsync everysec
save ""
maxmemory 2gb
maxmemory-policy allkeys-lru
EOF
  done

  for bus in system market intel; do
    local port
    case "$bus" in
      system) port=6379;;
      market) port=6380;;
      intel)  port=6381;;
    esac
    log "🚀 Starting Redis $bus ($port)" "INFO"
    sudo redis-server "/usr/local/etc/redis/$bus.conf" --daemonize yes
    wait_for_port "$port"
  done

  log "🧩 Reinjection of Truth across rebuilt buses" "INFO"
  for p in "${REDIS_PORTS[@]}"; do inject_truth "$p" "$DEFAULT_TRUTH"; done
  show_summary
  log "🎯 Rebuild complete and verified." "OK"
}

show_summary() {
  log "─────────────────────────────" "INFO"
  for p in "${REDIS_PORTS[@]}"; do
    redis-cli -p "$p" PING >/dev/null 2>&1 && log "✔ $p healthy" "OK" || log "❌ $p unreachable" "ERROR"
  done
  log "─────────────────────────────" "INFO"
}

# ──────────────────────────────────────────────
mode="${1:-inject}"
truth_file="${2:-$DEFAULT_TRUTH}"

case "$mode" in
  --inject|inject)   log "📜 Mode: inject"; for p in "${REDIS_PORTS[@]}"; do wait_for_port "$p"&&inject_truth "$p" "$truth_file"||log "Skip $p (offline)" "WARN";done;show_summary;;
  --verify|verify)   log "📜 Mode: verify"; for p in "${REDIS_PORTS[@]}"; do wait_for_port "$p"&&verify_truth "$p" "$truth_file";done;show_summary;;
  --diagnose|diagnose) log "📜 Mode: diagnose"; for p in "${REDIS_PORTS[@]}"; do diagnose_truth "$p";done;show_summary;;
  --heal|heal)       self_heal;show_summary;;
  --rebuild|rebuild) rebuild_environment;;
  --help|-h) cat <<EOF
🧭 inject-truth.sh v3.0 — Antifragile + Rebuild

Usage:
  ./inject-truth.sh [mode] [file]

Modes:
  inject     → seed or update Truth (default)
  verify     → verify hash & presence
  diagnose   → report system health
  heal       → auto-repair drift
  rebuild    → full teardown + reinstall + reinjection
  help       → show this help
EOF
  ;;
  *) log "❌ Unknown mode $mode" "ERROR"; exit 1;;
esac