#!/opt/homebrew/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
DL="$ROOT/services/massive/utils/massive_historical_options.py"

SYMBOLS="I:SPX SPY QQQ I:NDX"
DAYS_BACK=5
STRIKE_WINDOW=0.05
INTERVAL_SECONDS=60
OUT_DIR="$ROOT"
API_KEY="YOUR_API_KEY_HERE"

line(){ echo "──────────────────────────────────────────────────"; }

menu(){
  clear
  line
  echo "   Massive Historical Options Downloader"
  line
  echo "1) Set symbols (cur: $SYMBOLS)"
  echo "2) Set days back (cur: $DAYS_BACK)"
  echo "3) Set strike window (cur: $STRIKE_WINDOW)"
  echo "4) Set interval seconds (cur: $INTERVAL_SECONDS)"
  echo "5) Set output directory (cur: $OUT_DIR)"
  echo "6) Run downloader"
  echo "x) Quit"
  line
  read -rp "Choice: " CH
  case "$CH" in
    1) read -rp "Symbols: " SYMBOLS ;;
    2) read -rp "Days back: " DAYS_BACK ;;
    3) read -rp "Strike window (e.g. .05): " STRIKE_WINDOW ;;
    4) read -rp "Interval seconds: " INTERVAL_SECONDS ;;
    5) read -rp "Output directory: " OUT_DIR ;;
    6) run_downloader ;;
    x) exit 0 ;;
  esac
  menu
}

run_downloader(){
  clear
  line
  echo "Running historical downloader…"
  line
  $PY "$DL" \
    --symbols "$SYMBOLS" \
    --days-back "$DAYS_BACK" \
    --strike-window "$STRIKE_WINDOW" \
    --interval "$INTERVAL_SECONDS" \
    --out-dir "$OUT_DIR" \
    --api-key "$API_KEY"
  read -n1 -p "Done. Press any key…"
}

menu