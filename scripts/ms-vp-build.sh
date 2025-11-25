#!/opt/homebrew/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python3"
DL="$ROOT/services/massive/utils/massive_downloader.py"

API_KEY="YOUR_HARDCODED_API_KEY_HERE"
OUT_DIR="$ROOT/data"
SYMBOLS="SPX SPY QQQ NDX"
INTERVAL=1
DAYS=1
STRIKE_WINDOW=0.05

line() { echo "──────────────────────────────────────────────────"; }

menu() {
  clear
  line
  echo "   Massive Options Snapshot Downloader"
  line
  echo "1) Set symbols (cur: $SYMBOLS)"
  echo "2) Set days back (cur: $DAYS)"
  echo "3) Set interval seconds (cur: $INTERVAL)"
  echo "4) Set strike window (cur: $STRIKE_WINDOW)"
  echo "5) Set output directory (cur: $OUT_DIR)"
  echo "6) Run downloader"
  echo "x) Quit"
  line
  read -rp "Choice: " CH

  case "$CH" in
    1) set_symbols ;;
    2) set_days ;;
    3) set_interval ;;
    4) set_window ;;
    5) set_outdir ;;
    6) run_downloader ;;
    x) exit 0 ;;
  esac
}

set_symbols() {
  read -rp "Enter symbols (e.g. SPX SPY QQQ NDX): " SYMBOLS
  menu
}

set_days() {
  read -rp "Enter days back: " DAYS
  menu
}

set_interval() {
  read -rp "Enter interval seconds: " INTERVAL
  menu
}

set_window() {
  read -rp "Enter strike window (e.g. 0.05): " STRIKE_WINDOW
  menu
}

set_outdir() {
  read -rp "Enter output directory: " OUT_DIR
  menu
}

run_downloader() {
  clear
  line
  echo "Running snapshot downloader…"
  line
  $PY "$DL" \
      --symbols "$SYMBOLS" \
      --days "$DAYS" \
      --interval "$INTERVAL" \
      --strike-window "$STRIKE_WINDOW" \
      --out-dir "$OUT_DIR" \
      --api-key "$API_KEY"
  read -n1 -p "Done. Press any key…"
  menu
}

menu
