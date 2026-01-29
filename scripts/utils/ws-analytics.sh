#!/usr/bin/env bash
set -euo pipefail

###############################################
# Massive – WS Stream & Analytics Console
###############################################

# Defaults (override in-session)
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6380}"

WS_STREAM_KEY="${WS_STREAM_KEY:-massive:ws:stream}"
WS_ANALYTICS_KEY="${WS_ANALYTICS_KEY:-massive:ws:analytics}"

###############################################
# Helpers
###############################################

redis() {
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" "$@"
}

pause() {
  read -rp "Press ENTER to continue..."
}

header() {
  clear
  echo "──────────────────────────────────────────────"
  echo " Massive – WS Stream & Analytics"
  echo "──────────────────────────────────────────────"
  echo ""
}

show_config() {
  echo "Current configuration:"
  echo "  Redis Host      : $REDIS_HOST"
  echo "  Redis Port      : $REDIS_PORT"
  echo "  WS Stream Key   : $WS_STREAM_KEY"
  echo "  Analytics Key   : $WS_ANALYTICS_KEY"
  echo ""
}

###############################################
# Views
###############################################

view_stream_info() {
  header
  show_config
  echo "=== STREAM INFO ==="
  echo ""
  redis XINFO STREAM "$WS_STREAM_KEY"
  echo ""
  pause
}

view_stream_tail() {
  header
  show_config
  read -rp "How many entries to show? [default 5]: " n
  n="${n:-5}"
  echo ""
  # FIX: use XREVRANGE to get most recent entries
  redis XREVRANGE "$WS_STREAM_KEY" + - COUNT "$n"
  echo ""
  pause
}

view_stream_head() {
  header
  show_config
  read -rp "How many entries to show? [default 5]: " n
  n="${n:-5}"
  echo ""
  redis XRANGE "$WS_STREAM_KEY" - + COUNT "$n"
  echo ""
  pause
}

view_consumer_groups() {
  header
  show_config
  echo "=== CONSUMER GROUPS ==="
  echo ""
  redis XINFO GROUPS "$WS_STREAM_KEY"
  echo ""
  pause
}

view_consumers() {
  header
  show_config
  read -rp "Consumer group name: " group
  echo ""
  redis XINFO CONSUMERS "$WS_STREAM_KEY" "$group"
  echo ""
  pause
}

view_ws_analytics() {
  header
  show_config
  echo "=== WS ANALYTICS ==="
  echo ""
  redis HGETALL "$WS_ANALYTICS_KEY" | sed 'N;s/\n/ = /'
  echo ""
  pause
}

###############################################
# Actions
###############################################

trim_stream_len() {
  header
  show_config
  read -rp "Max stream length (approx): " maxlen
  echo ""
  redis XTRIM "$WS_STREAM_KEY" MAXLEN "~" "$maxlen"
  echo "Stream trimmed."
  pause
}

trim_stream_time() {
  header
  show_config
  read -rp "Keep how many seconds of history? " seconds
  now_ms=$(date +%s000)
  min_id=$((now_ms - seconds * 1000))
  echo ""
  redis XTRIM "$WS_STREAM_KEY" MINID "~" "$min_id"
  echo "Stream trimmed."
  pause
}

configure() {
  header
  show_config

  read -rp "New Redis host (blank = keep): " v
  [[ -n "$v" ]] && REDIS_HOST="$v"

  read -rp "New Redis port (blank = keep): " v
  [[ -n "$v" ]] && REDIS_PORT="$v"

  read -rp "New WS stream key (blank = keep): " v
  [[ -n "$v" ]] && WS_STREAM_KEY="$v"

  read -rp "New analytics key (blank = keep): " v
  [[ -n "$v" ]] && WS_ANALYTICS_KEY="$v"

  echo ""
  echo "Configuration updated."
  pause
}

###############################################
# Main Menu
###############################################

menu() {
  while true; do
    header
    show_config

    echo "Views:"
    echo "  1) Stream info (length, IDs, radix tree)"
    echo "  2) Show stream HEAD"
    echo "  3) Show stream TAIL"
    echo "  4) Consumer groups"
    echo "  5) Consumers in group"
    echo "  6) WS analytics"
    echo ""
    echo "Actions:"
    echo "  t) Trim stream by length"
    echo "  T) Trim stream by time"
    echo "  c) Configure"
    echo "  q) Quit"
    echo ""
    read -rp "Choose [1-6,t,T,c,q]: " choice

    case "$choice" in
      1) view_stream_info ;;
      2) view_stream_head ;;
      3) view_stream_tail ;;
      4) view_consumer_groups ;;
      5) view_consumers ;;
      6) view_ws_analytics ;;
      t) trim_stream_len ;;
      T) trim_stream_time ;;
      c|C) configure ;;
      q|Q) exit 0 ;;
      *) echo "Invalid choice"; sleep 1 ;;
    esac
  done
}

menu