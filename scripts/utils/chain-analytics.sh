#!/usr/bin/env bash
set -euo pipefail

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6380}"
BASE_KEY="massive:chain:analytics"

redis() {
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" "$@"
}

avg_from_zset() {
  redis ZRANGE "$1" 0 -1 | awk '{sum+=$1; n+=1} END { if (n>0) printf "%.4f\n", sum/n; else print "nil"}'
}

header() {
  clear
  echo "──────────────────────────────────────────────"
  echo " Massive – Chain Analytics (Extended)"
  echo "──────────────────────────────────────────────"
  echo ""
}

view_core() {
  header
  echo "=== CORE COUNTERS ==="
  redis HGETALL "$BASE_KEY" | sed 'N;s/\n/ = /'
  echo ""
  read -rp "ENTER..."
}

view_latency() {
  header
  echo "Average latency (ms): $(avg_from_zset "$BASE_KEY:fetch_latency")"
  echo "Min latency (ms): $(redis ZRANGE "$BASE_KEY:fetch_latency" 0 0)"
  echo "Max latency (ms): $(redis ZRANGE "$BASE_KEY:fetch_latency" -1 -1)"
  read -rp "ENTER..."
}

view_density() {
  header
  echo "Average contract density: $(avg_from_zset "$BASE_KEY:contract_density")"
  read -rp "ENTER..."
}

view_coverage() {
  header
  echo "=== SYMBOL COVERAGE ==="
  redis HGETALL "$BASE_KEY:symbol_coverage" | sed 'N;s/\n/ expirations = /'
  read -rp "ENTER..."
}

view_health() {
  header
  echo "=== FETCH HEALTH ==="
  redis HGETALL "$BASE_KEY:fetch_health" | sed 'N;s/\n/ = /'
  read -rp "ENTER..."
}

menu() {
  while true; do
    header
    echo "1) Core counters"
    echo "2) Latency"
    echo "3) Contract density"
    echo "4) Coverage"
    echo "5) Fetch health"
    echo "q) Quit"
    read -rp "Choose: " c
    case "$c" in
      1) view_core ;;
      2) view_latency ;;
      3) view_density ;;
      4) view_coverage ;;
      5) view_health ;;
      q) exit 0 ;;
    esac
  done
}

menu