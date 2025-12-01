#!/opt/homebrew/bin/bash
set -euo pipefail

BREW_REDIS="/opt/homebrew/bin/redis-cli"

line() { echo "──────────────────────────────────────────────"; }

read_stats() {
  $BREW_REDIS -h 127.0.0.1 -p 6381 HGETALL "rss:stats"
}

menu() {
  clear
  line
  echo " MarketSwarm – Aggregator Statistics"
  line
  echo "1) Ingest Stats"
  echo "2) Canonical Stats"
  echo "3) Raw Fetch Stats"
  echo "4) All Stats"
  echo "5) Exit"
  line
  read -rp "Choice: " CH
}

pretty_time() {
  if [[ -z "$1" ]]; then echo "n/a"; return; fi
  date -r "$1" "+%Y-%m-%d %H:%M:%S"
}

show_ingest() {
  clear
  line
  echo " Ingest Stats"
  line
  stats=$(read_stats)
  found=$(echo "$stats" | awk '/ingest_found/{print $2}')
  saved=$(echo "$stats" | awk '/ingest_saved/{print $2}')
  reject=$(echo "$stats" | awk '/ingest_rejected/{print $2}')
  ts=$(echo "$stats" | awk '/last_ingest_ts/{print $2}')

  echo "Found:     $found"
  echo "Saved:     $saved"
  echo "Rejected:  $reject"
  echo "Last Run:  $(pretty_time "$ts")"
  read -n1 -s -r -p "Press any key..."
}

show_canonical() {
  clear
  line
  echo " Canonical Stats"
  line
  stats=$(read_stats)
  ok=$(echo "$stats" | awk '/canonical_success/{print $2}')
  netfail=$(echo "$stats" | awk '/canonical_fail_network/{print $2}')
  parsefail=$(echo "$stats" | awk '/canonical_fail_parse/{print $2}')
  ts=$(echo "$stats" | awk '/last_canonical_ts/{print $2}')

  echo "Success:        $ok"
  echo "Net Failures:   $netfail"
  echo "Parse Failures: $parsefail"
  echo "Last Run:       $(pretty_time "$ts")"
  read -n1 -s -r -p "Press any key..."
}

show_raw() {
  clear
  line
  echo " Raw Fetch Stats"
  line
  stats=$(read_stats)
  ok=$(echo "$stats" | awk '/raw_success/{print $2}')
  netfail=$(echo "$stats" | awk '/raw_fail_network/{print $2}')
  short=$(echo "$stats" | awk '/raw_fail_short/{print $2}')
  ts=$(echo "$stats" | awk '/last_raw_ts/{print $2}')

  echo "Success:       $ok"
  echo "Network Fail:  $netfail"
  echo "Short HTML:    $short"
  echo "Last Run:      $(pretty_time "$ts")"
  read -n1 -s -r -p "Press any key..."
}

show_all() {
  clear
  line
  echo " FULL SYSTEM STATS"
  line
  read_stats | sed 's/ /: /g'
  read -n1 -s -r -p "Press any key..."
}

while true; do
  menu
  case "$CH" in
    1) show_ingest ;;
    2) show_canonical ;;
    3) show_raw ;;
    4) show_all ;;
    5) exit 0 ;;
    *) sleep 1 ;;
  esac
done