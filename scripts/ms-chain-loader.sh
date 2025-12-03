#!/opt/homebrew/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
CHAIN_LOADER="$ROOT/services/massive/utils/massive_chain_loader.py"

# Default configuration
SYMBOLS="I:SPX I:NDX SPY QQQ"
STRIKE_RANGE=150
REDIS_PREFIX="chain"
API_KEY="pdjraOWSpDbg3ER_RslZYe3dmn4Y7WCC"
REDIS_URL="redis://127.0.0.1:6380"
USE_STRICT_GT_LT="false"
NUM_EXPIRATIONS=10

line(){ echo "──────────────────────────────────────────────────"; }

menu(){
  clear
  line
  echo "         MarketSwarm — Massive Chain Loader"
  line
  echo "1)  Set symbols            (cur: $SYMBOLS)"
  echo "2)  Set strike ±range      (cur: $STRIKE_RANGE)"
  echo "3)  Set Redis prefix       (cur: $REDIS_PREFIX)"
  echo "4)  Set Massive API key    (cur: $API_KEY)"
  echo "5)  Set Redis URL          (cur: $REDIS_URL)"
  echo "6)  GT/LT strict mode      (cur: $USE_STRICT_GT_LT)"
  echo "7)  Number of expirations  (cur: $NUM_EXPIRATIONS)"
  echo "8)  View chains in Redis"
  echo "9)  Run chain loader"
  echo "x)  Quit"
  line

  read -rp "Choice: " CH
  case "$CH" in
    1) read -rp "Symbols (e.g. I:SPX I:NDX SPY QQQ): " SYMBOLS ;;
    2) read -rp "Strike ±range (e.g. 150): " STRIKE_RANGE ;;
    3) read -rp "Redis prefix (e.g. chain): " REDIS_PREFIX ;;
    4) read -rp "Massive API key: " API_KEY ;;
    5) read -rp "Redis URL (e.g. redis://127.0.0.1:6380): " REDIS_URL ;;
    6) toggle_strict_mode ;;
    7) read -rp "Number of expirations (e.g. 10): " NUM_EXPIRATIONS ;;
    8) visualize_chain ;;
    9) run_loader ;;
    x) exit 0 ;;
  esac
  menu
}

toggle_strict_mode(){
  if [[ "$USE_STRICT_GT_LT" == "false" ]]; then
    USE_STRICT_GT_LT="true"
  else
    USE_STRICT_GT_LT="false"
  fi
}

run_loader(){
  clear
  line
  echo "Running Massive chain loader…"
  line

  # Pass args into Python script
  $PY "$CHAIN_LOADER" \
    --symbols "$SYMBOLS" \
    --strike-range "$STRIKE_RANGE" \
    --redis-prefix "$REDIS_PREFIX" \
    --api-key "$API_KEY" \
    --strict "$USE_STRICT_GT_LT" \
    --expirations "$NUM_EXPIRATIONS" \
    --redis-url "$REDIS_URL"

  echo ""
  read -n1 -p "Done. Press any key…"
}


visualize_chain(){
  clear
  line
  echo "Redis Chain Visualization"
  line

  echo "Available Redis chain keys:"
  redis-cli -u "$REDIS_URL" KEYS "${REDIS_PREFIX}:*" | sed 's/^/ - /'

  echo ""
  read -rp "Enter key to inspect (blank to return): " KEY
  [[ -z "$KEY" ]] && return

  clear
  line
  echo "Contents for Redis key: $KEY"
  line

  redis-cli -u "$REDIS_URL" HGETALL "$KEY" | \
    awk 'NR%2==1{printf("\n%s → ", $0)} NR%2==0{print $0}'

  echo ""
  read -n1 -p "Press any key to return…"
}

menu