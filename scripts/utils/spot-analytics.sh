#!/usr/bin/env bash

REDIS_HOST="127.0.0.1"
REDIS_PORT="6380"
KEY="massive:spot:analytics"

print_report() {

  # STEP 1: GET DATA EXACTLY THE WAY YOU PROVED WORKS
  JSON=$(
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HGETALL "$KEY" | \
    python3 -c "import sys,json; data=sys.stdin.read().splitlines(); print(json.dumps(dict(zip(data[::2], data[1::2]))))"
  )

  # STEP 2: FORMAT IT
  python3 - <<EOF
import json
from collections import defaultdict

data = json.loads('''$JSON''')

if not data:
    print("No analytics data present.")
    exit(0)

by_symbol = defaultdict(dict)

for k, v in data.items():
    sym, metric = k.split("_", 1)
    by_symbol[sym][metric] = v

print()
print(f"{'SYM':<6}{'COUNT':>10}{'AVG(s)':>12}")
print("-" * 28)

for sym in sorted(by_symbol):
    count = int(by_symbol[sym].get("spot_fetch_count", 0))
    avg   = float(by_symbol[sym].get("spot_fetch_avg", 0))
    print(f"{sym:<6}{count:>10}{avg:>12.6f}")

print()
EOF
}

zero_out() {
  read -p "This will DELETE $KEY. Are you sure? (y/N): " confirm
  if [[ "$confirm" =~ ^[Yy]$ ]]; then
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DEL "$KEY" > /dev/null
    echo "Analytics reset complete."
  else
    echo "Aborted."
  fi
}

while true; do
  echo
  echo "Spot Analytics Menu"
  echo "-------------------"
  echo "1) Show analytics report"
  echo "2) Zero out analytics"
  echo "3) Exit"
  echo
  read -p "Select option: " choice

  case "$choice" in
    1) print_report ;;
    2) zero_out ;;
    3) exit 0 ;;
    *) echo "Invalid selection." ;;
  esac
done