#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – Truth Bootstrapper
# Menu-driven operator UI
###############################################

# ------------------------------------------------
# Path resolution (run from project root)
# ------------------------------------------------
PROJECT_ROOT="$(pwd)"
TRUTH_FILE="${PROJECT_ROOT}/scripts/truth.json"

###############################################
# Preconditions
###############################################
command -v jq >/dev/null 2>&1 || {
  echo "[ERROR] jq is required" >&2
  exit 1
}

REDIS_CLI="$(command -v redis-cli || true)"
[[ -x "$REDIS_CLI" ]] || {
  echo "[ERROR] redis-cli not found in PATH" >&2
  exit 1
}

[[ -f "$TRUTH_FILE" ]] || {
  echo "[ERROR] truth.json not found:"
  echo "  Expected at: $TRUTH_FILE"
  exit 1
}

###############################################
# Resolve Redis buses from truth.json (URL-based)
###############################################
readarray -t REDIS_BUSES < <(
  jq -r '
    .buses
    | to_entries[]
    | select(.value.url | startswith("redis://"))
    | .key + "|" + .value.role + "|" +
      (.value.url | sub("^redis://"; "") )
  ' "$TRUTH_FILE"
)

###############################################
# Helpers
###############################################
redis_ping() {
  local host="$1" port="$2"
  "$REDIS_CLI" -h "$host" -p "$port" PING 2>/dev/null
}

port_listening() {
  local port="$1"
  lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

###############################################
# Status display (ACTUAL runtime state)
###############################################
show_status() {
  echo "Redis Buses (from truth.json):"
  echo ""

  for entry in "${REDIS_BUSES[@]}"; do
    IFS='|' read -r key role endpoint <<< "$entry"
    host="${endpoint%%:*}"
    port="${endpoint##*:}"

    status="UNKNOWN"

    if port_listening "$port"; then
      if [[ "$(redis_ping "$host" "$port")" == "PONG" ]]; then
        status="RUNNING"
      else
        status="LISTENING (no PONG)"
      fi
    else
      status="NOT RUNNING"
    fi

    printf "  %-14s %-8s %s:%s  [%s]\n" \
      "$key" "$role" "$host" "$port" "$status"
  done
}

###############################################
# Redis command helpers (bus-aware)
###############################################
rc_bus() {
  local bus_key="$1"; shift
  local entry
  entry="$(printf "%s\n" "${REDIS_BUSES[@]}" | grep "^${bus_key}|")" || {
    echo "[ERROR] Redis bus not found: $bus_key"
    return 1
  }

  IFS='|' read -r _ _ endpoint <<< "$entry"
  "$REDIS_CLI" -h "${endpoint%%:*}" -p "${endpoint##*:}" "$@"
}

###############################################
# Core Actions
###############################################
load_truth() {
  clear
  echo "Loading Truth into system-redis"
  echo "────────────────────────────────"
  show_status
  echo ""

  rc_bus system-redis SET truth "$(cat "$TRUTH_FILE")" >/dev/null \
    || { echo "[ERROR] Failed to write truth"; sleep 2; return; }

  rc_bus system-redis PING | grep -q PONG \
    || { echo "[ERROR] system-redis not responding"; sleep 2; return; }

  echo ""
  echo "[OK] Truth loaded and verified"
  sleep 2
}

verify_status() {
  clear
  echo "Verifying MarketSwarm Truth State"
  echo "─────────────────────────────────"
  show_status
  echo ""

  if rc_bus system-redis EXISTS truth | grep -q '^1$'; then
    echo "[OK] Truth present in system-redis"
  else
    echo "[WARN] Truth missing in system-redis"
  fi

  echo ""
  read -rp "Press Enter to continue..."
}

###############################################
# NEW: Clear Redis Busses (Pristine)
###############################################
clear_redis_busses() {
  clear
  echo "⚠️  CLEAR ALL REDIS BUSSES (PRISTINE)"
  echo "────────────────────────────────────"
  show_status
  echo ""
  echo "This will FLUSHALL on each reachable Redis bus."
  echo "Data will be permanently deleted."
  echo ""
  read -rp "Type CLEAR to confirm: " confirm

  [[ "$confirm" == "CLEAR" ]] || {
    echo "Aborted."
    sleep 2
    return
  }

  echo ""
  for entry in "${REDIS_BUSES[@]}"; do
    IFS='|' read -r key role endpoint <<< "$entry"
    host="${endpoint%%:*}"
    port="${endpoint##*:}"

    if [[ "$(redis_ping "$host" "$port")" == "PONG" ]]; then
      echo "Clearing $key ($host:$port)..."
      "$REDIS_CLI" -h "$host" -p "$port" FLUSHALL >/dev/null
      echo "  [OK] Cleared"
    else
      echo "Skipping $key ($host:$port) – not reachable"
    fi
  done

  echo ""
  echo "[DONE] Redis busses cleared"
  sleep 2
}

###############################################
# Interactive Menu
###############################################
menu() {
  while true; do
    clear
    echo "──────────────────────────────────────────────"
    echo " MarketSwarm – Truth Bootstrapper"
    echo "──────────────────────────────────────────────"
    echo ""
    show_status
    echo ""
    echo "Actions:"
    echo "  1) Load Truth (system-redis)"
    echo "  2) Verify truth presence"
    echo "  3) Clear Redis busses (PRISTINE)"
    echo ""
    echo "  q) Quit"
    echo ""
    echo "──────────────────────────────────────────────"
    read -rp "Choose [1-3,q]: " choice

    case "$choice" in
      1) load_truth ;;
      2) verify_status ;;
      3) clear_redis_busses ;;
      q|Q)
        echo "Goodbye"
        exit 0
        ;;
      *)
        echo "Invalid choice"
        sleep 1
        ;;
    esac
  done
}

###############################################
# Entrypoint
###############################################
case "${1:-}" in
  --load)
    echo "Loading Truth into system-redis (non-interactive)"
    echo "────────────────────────────────────────────────"
    show_status
    echo ""
    rc_bus system-redis SET truth "$(cat "$TRUTH_FILE")" >/dev/null \
      || { echo "[ERROR] Failed to write truth"; exit 1; }
    rc_bus system-redis PING | grep -q PONG \
      || { echo "[ERROR] system-redis not responding after write"; exit 1; }
    echo "[OK] Truth loaded and verified"
    ;;
  *)
    menu
    ;;
esac