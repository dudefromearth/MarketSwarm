#!/usr/bin/env bash
#
# mmaker-startup.sh — Interactive warm-up and diagnostic runner
#

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
export PYTHONPATH="$ROOT/services:$ROOT"

REDIS_PORT=6380
UNDERLYING="SPX"
EXPIRY_YYYYMMDD=$(date +"%Y%m%d")
EXPIRY_ISO=$(date +"%Y-%m-%d")

RAW_STREAM="massive:trades:${UNDERLYING}:${EXPIRY_YYYYMMDD}"
SPOT_KEY="massive:model:spot:${UNDERLYING}"

# ----------------------------------------------
# MENU
# ----------------------------------------------

show_menu() {
  clear
  echo "──────────────────────────────────────────────────────"
  echo "  mmaker Startup Ingestion Menu"
  echo "──────────────────────────────────────────────────────"
  echo "ROOT        : $ROOT"
  echo "PYTHON      : $PY"
  echo "REDIS PORT  : $REDIS_PORT"
  echo "UNDERLYING  : $UNDERLYING"
  echo "EXPIRY      : $EXPIRY_YYYYMMDD ($EXPIRY_ISO)"
  echo "RAW STREAM  : $RAW_STREAM"
  echo ""
  echo "1) Run warmup (SingleContract + Butterfly)"
  echo "2) Run warmup (SingleContract only)"
  echo "3) Run warmup (Butterfly only)"
  echo "4) Show raw stream stats"
  echo "5) Show spot"
  echo "6) Run full mmaker after warmup"
  echo "7) Exit"
  echo ""
  read -p "Select option: " choice
}

# ----------------------------------------------
# HELPERS
# ----------------------------------------------

show_raw_stats() {
  echo ""
  COUNT=$(redis-cli -p $REDIS_PORT XLEN "$RAW_STREAM")
  echo "Raw trades in $RAW_STREAM → $COUNT"
  echo ""
  read -p "Press Enter to continue..."
}

show_spot() {
  echo ""
  redis-cli -p $REDIS_PORT GET "$SPOT_KEY"
  echo ""
  read -p "Press Enter to continue..."
}

# ----------------------------------------------
# PYTHON WARM-UP EXECUTION BLOCK
# ----------------------------------------------

run_py() {
$PY <<EOF
import asyncio, json
import redis.asyncio as redis

from services.mmaker.intel.startup_ingestor import StartupIngestor
from services.mmaker.intel.single_contract import SingleContractTransformer
from services.mmaker.intel.butterfly import ButterflyTransformer

r = redis.Redis(host="127.0.0.1", port=$REDIS_PORT, decode_responses=True)

config = {
    "underlying": "$UNDERLYING",
    "expiry_iso": "$EXPIRY_ISO",
    "expiry_yyyymmdd": "$EXPIRY_YYYYMMDD",
    "redis_market": r,
    "redis_market_url": "redis://127.0.0.1:$REDIS_PORT"
}

async def main():
    ing = StartupIngestor(r, "$RAW_STREAM")
    trades = await ing.load_recent_trades(limit=$1)

    transformers = []
    if $2 == 1:
        transformers.append(SingleContractTransformer(config))
    if $3 == 1:
        transformers.append(ButterflyTransformer(config))

    print("\\nFeeding warm-up trades to transformers...")
    await ing.feed_transformers(trades, transformers)

    for t in transformers:
        print("\\n────────────────────────────")
        print(f"MODEL → {t.name}")
        print("────────────────────────────")
        raw = await r.get(t.model_key)
        if raw:
            print(json.dumps(json.loads(raw), indent=2))
        else:
            print("⚠️ No model output produced.")

asyncio.run(main())
EOF
}

# ----------------------------------------------
# MAIN LOOP
# ----------------------------------------------

while true; do
  show_menu
  case $choice in

    1)
      echo "Running warmup: Single + Butterfly"
      run_py 2000 1 1
      read -p "Press Enter to continue..."
      ;;

    2)
      echo "Running warmup: SingleContract only"
      run_py 2000 1 0
      read -p "Press Enter to continue..."
      ;;

    3)
      echo "Running warmup: Butterfly only"
      run_py 2000 0 1
      read -p "Press Enter to continue..."
      ;;

    4)
      show_raw_stats
      ;;

    5)
      show_spot
      ;;

    6)
      echo "Launching full mmaker..."
      exec "$ROOT/scripts/run-mm.sh"
      ;;

    7)
      echo "Exiting."
      exit 0
      ;;

    *)
      echo "Invalid choice."
      ;;

  esac
done