#!/usr/bin/env bash

# ======================================================
#  MASSIVE — Volume Profile Chart Generator Menu
# ======================================================
#  Generates a JPEG chart from volume_profile.json.
#  Supports RAW vs TV dataset + struct on/off + JSON dump.
# ======================================================

# ------------------------------------------------------
# Path Resolution
# ------------------------------------------------------
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PY_SCRIPT="${PROJECT_ROOT}/services/massive/utils/volume_profile_chart.py"
DATA_FILE="${PROJECT_ROOT}/volume_profile.json"

# ------------------------------------------------------
# Sanity Checks
# ------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ Python3 not found. Install Python3 first."
  exit 1
fi

if [[ ! -f "$PY_SCRIPT" ]]; then
  echo "❌ volume_profile_chart.py not found:"
  echo "   $PY_SCRIPT"
  exit 1
fi

if [[ ! -f "$DATA_FILE" ]]; then
  echo "❌ volume_profile.json not found:"
  echo "   $DATA_FILE"
  echo "Export it with:"
  echo "  redis-cli -n 0 GET massive:volume_profile > volume_profile.json"
  exit 1
fi


# ------------------------------------------------------
# Rendering Helper
# ------------------------------------------------------
render_chart() {
  local MODE="$1"
  local OUT="$2"
  shift 2

  local DUMP_FLAG=""

  # Ask whether to dump JSON
  read -p "Dump JSON dataset? (y/N): " DUMP
  if [[ "$DUMP" =~ ^[Yy]$ ]]; then
    DUMP_FLAG="--dump-json"
  fi

  echo ""
  echo "🎨 Rendering ($MODE) → $OUT"

  python3 "$PY_SCRIPT" \
    --input "$DATA_FILE" \
    --mode "$MODE" \
    --output "$OUT" \
    $DUMP_FLAG \
    "$@"
}


# ------------------------------------------------------
# Menu-driven modes
# ------------------------------------------------------

run_default() {
  read -p "Structural analysis on/off (default on): " S
  if [[ "$S" =~ ^[Nn]$ ]]; then
      STRUCT="off"
  else
      STRUCT="on"
  fi

  render_chart raw "chart_raw.jpg" \
    --range-auto \
    --orientation right \
    --struct "$STRUCT"
}

run_custom_size() {
  read -p "Image width (default 900): " WIDTH
  read -p "Image height (default 1400): " HEIGHT
  read -p "Mode raw/tv (default raw): " MODE
  read -p "Structural analysis on/off (default on): " STRUCT

  render_chart "${MODE:-raw}" "chart_${MODE:-raw}.jpg" \
    --width "${WIDTH:-900}" \
    --height "${HEIGHT:-1400}" \
    --range-auto \
    --orientation right \
    --struct "${STRUCT:-on}"
}

run_custom_struct() {
  read -p "Mode raw/tv (default raw): " MODE
  read -p "Structural analysis on/off (default on): " STRUCT
  read -p "Structural threshold (default 2.0): " THR

  render_chart "${MODE:-raw}" "chart_${MODE:-raw}.jpg" \
    --struct "${STRUCT:-on}" \
    --struct-threshold "${THR:-2.0}" \
    --range-auto \
    --orientation right
}

run_full_custom() {
  echo "--- FULL CUSTOM MODE ---"
  read -p "Mode raw/tv (default raw): " MODE
  read -p "Structural analysis on/off (default on): " STRUCT
  read -p "Structural threshold (default 2.0): " THR
  read -p "Image width (default 900): " WIDTH
  read -p "Image height (default 1400): " HEIGHT
  read -p "Orientation (left/right, default right): " ORIENT
  read -p "Output filename (default chart.jpg): " OUT
  read -p "Manual Range? (y/n, default n): " RANGE_CHOICE

  if [[ "$RANGE_CHOICE" =~ ^[Yy]$ ]]; then
    read -p "LOW price: " LOW
    read -p "HIGH price: " HIGH
    RANGE_ARGS=(--range "$LOW" "$HIGH")
  else
    RANGE_ARGS=(--range-auto)
  fi

  render_chart "${MODE:-raw}" "${OUT:-chart.jpg}" \
    --width "${WIDTH:-900}" \
    --height "${HEIGHT:-1400}" \
    --struct "${STRUCT:-on}" \
    --struct-threshold "${THR:-2.0}" \
    --orientation "${ORIENT:-right}" \
    "${RANGE_ARGS[@]}"
}

run_auto_range() {
  read -p "Mode raw/tv (default raw): " MODE
  read -p "Structural analysis on/off (default on): " STRUCT
  read -p "Orientation (left/right, default right): " ORIENT

  render_chart "${MODE:-raw}" "chart_${MODE:-raw}.jpg" \
    --range-auto \
    --orientation "${ORIENT:-right}" \
    --struct "${STRUCT:-on}"
}

run_manual_range() {
  read -p "Mode raw/tv (default raw): " MODE
  read -p "Structural analysis on/off (default on): " STRUCT
  read -p "LOW price: " LOW
  read -p "HIGH price: " HIGH
  read -p "Orientation (left/right, default right): " ORIENT

  render_chart "${MODE:-raw}" "chart_${MODE:-raw}.jpg" \
    --range "$LOW" "$HIGH" \
    --orientation "${ORIENT:-right}" \
    --struct "${STRUCT:-on}"
}


# ------------------------------------------------------
# Menu UI
# ------------------------------------------------------
clear_menu() {
  clear
  echo "======================================================="
  echo "      📊 MASSIVE — Volume Profile Chart Utility"
  echo "======================================================="
  echo
  echo "Data file: $DATA_FILE"
  echo
  echo " 1) Generate RAW Chart (Auto Range)"
  echo " 2) Custom Size + Mode"
  echo " 3) Struct Threshold + Mode"
  echo " 4) Full Custom Mode"
  echo
  echo " 5) Auto Range + Mode"
  echo " 6) Manual Range + Mode"
  echo
  echo " x) Exit"
  echo
  printf "> "
}

# ------------------------------------------------------
# Main Loop
# ------------------------------------------------------
while true; do
  clear_menu
  read choice

  case "$choice" in
    1) run_default ;;
    2) run_custom_size ;;
    3) run_custom_struct ;;
    4) run_full_custom ;;
    5) run_auto_range ;;
    6) run_manual_range ;;
    x|X) echo "Exiting." ; exit 0 ;;
    *) echo "Invalid option"; sleep 1 ;;
  esac
done