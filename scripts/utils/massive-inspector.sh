#!/usr/bin/env bash
# ============================================================
# MASSIVE :: Pipeline Inspector (Geometry-Authoritative)
# Model-Complete (Live + Replay)
# ============================================================

REDIS_PORT=6380
SYMBOLS=("I:SPX" "I:NDX")

pause() {
  echo
  read -rp "Press ENTER to continue..."
}

header() {
  clear
  echo "================================================="
  echo " MASSIVE :: PIPELINE INSPECTOR (Geometry)"
  echo " $(date)"
  echo " Redis Port: $REDIS_PORT"
  echo "================================================="
  echo
}

format_hset() {
  local key="$1"
  local data
  data=$(redis-cli -p $REDIS_PORT HGETALL "$key" 2>/dev/null)

  if [[ -z "$data" ]]; then
    echo "  (no data)"
    return
  fi

  echo "$data" | while read -r field; do
    read -r value
    printf "    %-40s %s\n" "$field" "$value"
  done
}

# ------------------------------------------------------------
# Chain Geometry State
# ------------------------------------------------------------
show_chain_state() {
  header
  echo "---- Chain Geometry ----"
  echo

  raw=$(redis-cli -p $REDIS_PORT GET massive:chain:latest)
  if [[ -z "$raw" ]]; then
    echo "  massive:chain:latest not present"
    pause
    return
  fi

  version=$(echo "$raw" | jq -r '.version')
  ts=$(echo "$raw" | jq -r '.ts')
  total=$(echo "$raw" | jq '.contracts | length')

  echo "  Version        : $version"
  echo "  Timestamp      : $ts"
  echo "  Total contracts: $total"
  echo

  echo "  Breakdown by ticker prefix:"
  echo "$raw" | jq -r '.contracts | keys[]' | \
    sed 's/^O://' | cut -c1-4 | sort | uniq -c | sed 's/^/    /'

  echo
  echo "---- Chain Analytics ----"
  format_hset "massive:chain:analytics"

  pause
}

# ------------------------------------------------------------
# Snapshot Stage
# ------------------------------------------------------------
show_snapshot_state() {
  header
  echo "---- Snapshot Stage ----"
  echo

  last_delta=$(redis-cli -p $REDIS_PORT GET massive:chain:delta:latest)

  if [[ -z "$last_delta" ]]; then
    echo "  No geometry delta published yet"
  else
    echo "  Last geometry delta:"
    echo "$last_delta" | jq
  fi

  pause
}

# ------------------------------------------------------------
# Builder Stage
# ------------------------------------------------------------
show_builder_state() {
  header
  echo "---- Builder Stage ----"
  echo

  for sym in "${SYMBOLS[@]}"; do
    echo "[$sym]"

    key="massive:heatmap:deltas:$sym"
    len=$(redis-cli -p $REDIS_PORT LLEN "$key")

    printf "    %-40s %s\n" "Delta queue length" "$len"

    if [[ "$len" -gt 0 ]]; then
      echo "    Last delta payload:"
      redis-cli -p $REDIS_PORT LRANGE "$key" -1 -1 | jq
    else
      echo "    (no deltas — geometry stable)"
    fi

    echo
  done

  echo "---- Builder Analytics ----"
  format_hset "massive:builder:analytics"

  pause
}

# ------------------------------------------------------------
# Model Stage (LIVE + REPLAY COMPLETENESS)
# ------------------------------------------------------------
show_model_state() {
  header
  echo "---- Model Publisher (Completeness) ----"
  echo

  for sym in "${SYMBOLS[@]}"; do
    echo "[$sym]"

    # Live model
    live_key="massive:heatmap:model:$sym:latest"
    live_exists=$(redis-cli -p $REDIS_PORT EXISTS "$live_key")
    live_ttl=$(redis-cli -p $REDIS_PORT TTL "$live_key")

    # Replay model (authoritative)
    replay_key="massive:heatmap:replay:$sym"
    replay_len=$(redis-cli -p $REDIS_PORT XLEN "$replay_key" 2>/dev/null)
    replay_exists=$([[ "$replay_len" =~ ^[0-9]+$ ]] && echo 1 || echo 0)
    replay_ttl=$(redis-cli -p $REDIS_PORT TTL "$replay_key")

    printf "    %-40s %s\n" "Live model exists" "$live_exists"
    printf "    %-40s %s\n" "Live TTL (sec)" "$live_ttl"
    echo
    printf "    %-40s %s\n" "Replay stream exists" "$replay_exists"
    printf "    %-40s %s\n" "Replay stream length" "$replay_len"
    printf "    %-40s %s\n" "Replay TTL (sec)" "$replay_ttl"

    if [[ "$replay_exists" -eq 0 ]]; then
      echo "    ⚠️  WARNING: Replay model missing — historical completeness broken"
    fi

    echo
  done

  echo "---- Model Analytics ----"
  format_hset "massive:model:analytics"

  pause
}

# ------------------------------------------------------------
# Health Summary
# ------------------------------------------------------------
show_health() {
  header
  echo "---- Pipeline Health ----"
  echo

  echo "Chain:"
  format_hset "massive:chain:analytics"
  echo

  echo "Builder:"
  format_hset "massive:builder:analytics"
  echo

  echo "Model:"
  format_hset "massive:model:analytics"

  pause
}

# ------------------------------------------------------------
# Menu
# ------------------------------------------------------------
main_menu() {
  while true; do
    header
    echo "Select an option:"
    echo
    echo " 1) Chain Geometry"
    echo " 2) Snapshot Events"
    echo " 3) Builder State"
    echo " 4) Model State (Live + Replay)"
    echo
    echo " a) Pipeline Health Summary"
    echo " r) Refresh"
    echo " 0) Exit"
    echo
    read -rp "Choice: " choice

    case "$choice" in
      1) show_chain_state ;;
      2) show_snapshot_state ;;
      3) show_builder_state ;;
      4) show_model_state ;;
      a) show_health ;;
      r) continue ;;
      0) clear; exit 0 ;;
      *) echo "Invalid choice"; sleep 1 ;;
    esac
  done
}

main_menu