#!/usr/bin/env bash

# ======================================================
#  MASSIVE — Volume Profile Chart Generator Menu
# ======================================================
#  Generates a JPEG/PNG chart from volume_profile.json.
#  Default orientation = RIGHT (price on right, bars left)
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

# ------------------------------------------------------
# Help Text
# ------------------------------------------------------
show_help() {
  clear
  echo "======================================================="
  echo "        📘 HELP — Volume Profile Chart Utility"
  echo "======================================================="
  echo
  echo "This tool renders a professional SPX Volume Profile"
  echo "based on the JSON file created by:"
  echo
  echo "    ./scripts/vp-backfill.sh"
  echo
  echo "--------------------------------------------------------"
  echo "  PRICE RANGE OPTIONS"
  echo "--------------------------------------------------------"
  echo "  --range-auto       (DEFAULT)"
  echo "       Auto crop: ATH → ATH - 250 points"
  echo
  echo "  --range LOW HIGH"
  echo "       Manual SPX price range"
  echo
  echo "--------------------------------------------------------"
  echo "  ORIENTATION OPTIONS"
  echo "--------------------------------------------------------"
  echo "  --orientation right   (DEFAULT, PROFESSIONAL MODE)"
  echo "       ✓ Price axis on RIGHT"
  echo "       ✓ Bars extend LEFT"
  echo "       ✓ Mirrored profile (matches trading platforms)"
  echo
  echo "  --orientation left"
  echo "       ✓ Price axis on LEFT"
  echo "       ✓ Bars extend RIGHT"
  echo
  echo "--------------------------------------------------------"
  echo "  NOTES"
  echo "--------------------------------------------------------"
  echo "• This tool produces a JPEG (chart.jpg) by default."
  echo "• Structural markers are disabled by default."
  echo "• Charts integrate perfectly with Vexy & front-end UI."
  echo
  echo "Press ENTER to return to menu."
  read
}

# ------------------------------------------------------
# Rendering Functions
# ------------------------------------------------------

run_default() {
  # Default: Auto-range + Mirrored orientation (bars LEFT)
  python3 "$PY_SCRIPT" \
    --input "$DATA_FILE" \
    --range-auto \
    --orientation right
}

run_custom_size() {
  read -p "Image width (default 900): " WIDTH
  read -p "Image height (default 1400): " HEIGHT
  read -p "Orientation (left/right, default right): " ORIENT

  python3 "$PY_SCRIPT" \
    --input "$DATA_FILE" \
    --width "${WIDTH:-900}" \
    --height "${HEIGHT:-1400}" \
    --range-auto \
    --orientation "${ORIENT:-right}"
}

run_custom_struct() {
  read -p "Structural threshold (default 2.0): " THR
  read -p "Orientation (left/right, default right): " ORIENT

  python3 "$PY_SCRIPT" \
    --input "$DATA_FILE" \
    --struct-threshold "${THR:-2.0}" \
    --range-auto \
    --orientation "${ORIENT:-right}"
}

run_full_custom() {
  read -p "Image width        (default 900):     " WIDTH
  read -p "Image height       (default 1400):    " HEIGHT
  read -p "Struct threshold   (default 2.0):     " THR
  read -p "Orientation (left/right, default right): " ORIENT
  read -p "Output filename    (default chart.jpg): " OUT

  python3 "$PY_SCRIPT" \
    --input "$DATA_FILE" \
    --width "${WIDTH:-900}" \
    --height "${HEIGHT:-1400}" \
    --struct-threshold "${THR:-2.0}" \
    --orientation "${ORIENT:-right}" \
    --output "${OUT:-chart.jpg}" \
    --range-auto
}

run_auto_range() {
  read -p "Orientation (left/right, default right): " ORIENT

  python3 "$PY_SCRIPT" \
    --input "$DATA_FILE" \
    --range-auto \
    --orientation "${ORIENT:-right}"
}

run_manual_range() {
  read -p "Enter LOW SPX price:  " LOW
  read -p "Enter HIGH SPX price: " HIGH
  read -p "Orientation (left/right, default right): " ORIENT

  python3 "$PY_SCRIPT" \
    --input "$DATA_FILE" \
    --range "$LOW" "$HIGH" \
    --orientation "${ORIENT:-right}"
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
  echo " 1) Generate Chart (Auto Range, Professional Mirrored Default)"
  echo " 2) Generate w/ Custom Image Size + Orientation"
  echo " 3) Generate w/ Structural Threshold + Orientation"
  echo " 4) Full Custom Mode"
  echo
  echo " 5) Auto Range (ATH → ATH−250) + Orientation"
  echo " 6) Manual Price Range + Orientation"
  echo
  echo " h) Help"
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
    h|H) show_help ;;
    x|X) echo "Exiting." ; exit 0 ;;
    *) echo "Invalid choice"; sleep 1 ;;
  esac
done