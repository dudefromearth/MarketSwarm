#!/opt/homebrew/bin/bash
set -euo pipefail

###############################################
# MarketSwarm – VP Dev Tool
# Quick injection of spot prices & VP buckets
# for Volume Profile Structural Tool development
###############################################

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$ROOT/.venv/bin/python"
DEV_SCRIPT="$ROOT/services/massive/intel/utils/vp_dev_injector.py"

export MARKET_REDIS_URL="${MARKET_REDIS_URL:-redis://127.0.0.1:6380}"

###############################################
# Helpers
###############################################
line() { printf '%.0s─' {1..50}; echo; }
header() {
    clear
    line
    echo " MarketSwarm – VP Dev Tool"
    line
}

pause() {
    echo ""
    read -rp "Press ENTER to continue..."
}

run_py() {
    cd "$ROOT"
    "$VENV_PY" "$DEV_SCRIPT" "$@"
}

###############################################
# Menu Actions
###############################################

show_current_state() {
    header
    echo ""
    echo "Current State:"
    line
    run_py --action show
    pause
}

inject_spot() {
    header
    echo ""
    echo "Inject Spot Price"
    line
    echo "Current spot:"
    run_py --action show-spot
    echo ""
    read -rp "Enter SPX spot price (e.g., 6900.50): " SPOT

    if [[ -z "$SPOT" ]]; then
        echo "No price entered. Aborting."
        pause
        return
    fi

    run_py --action inject-spot --value "$SPOT"
    pause
}

inject_vp_range() {
    header
    echo ""
    echo "Inject VP Range (uniform volume)"
    line
    echo "Creates VP buckets across a price range with uniform volume."
    echo ""
    read -rp "Start price (e.g., 6800): " START
    read -rp "End price (e.g., 7000): " END
    read -rp "Volume per bucket [1000000]: " VOL

    VOL="${VOL:-1000000}"

    if [[ -z "$START" || -z "$END" ]]; then
        echo "Invalid range. Aborting."
        pause
        return
    fi

    run_py --action inject-vp-range --start "$START" --end "$END" --volume "$VOL"
    pause
}

inject_vp_node() {
    header
    echo ""
    echo "Inject VP Node (high volume area)"
    line
    echo "Creates a cluster of high-volume buckets around a price level."
    echo ""
    read -rp "Center price (e.g., 6895): " CENTER
    read -rp "Width in points (e.g., 10 for +/-5): " WIDTH
    read -rp "Peak volume [10000000]: " VOL

    WIDTH="${WIDTH:-10}"
    VOL="${VOL:-10000000}"

    if [[ -z "$CENTER" ]]; then
        echo "Invalid price. Aborting."
        pause
        return
    fi

    run_py --action inject-vp-node --center "$CENTER" --width "$WIDTH" --volume "$VOL"
    pause
}

inject_vp_well() {
    header
    echo ""
    echo "Inject VP Well (low volume area)"
    line
    echo "Creates a cluster of LOW-volume buckets (antinode)."
    echo ""
    read -rp "Center price (e.g., 6945): " CENTER
    read -rp "Width in points (e.g., 10): " WIDTH
    read -rp "Volume [100000]: " VOL

    WIDTH="${WIDTH:-10}"
    VOL="${VOL:-100000}"

    if [[ -z "$CENTER" ]]; then
        echo "Invalid price. Aborting."
        pause
        return
    fi

    run_py --action inject-vp-well --center "$CENTER" --width "$WIDTH" --volume "$VOL"
    pause
}

inject_structure_preset() {
    header
    echo ""
    echo "Inject Structure Preset"
    line
    echo ""
    echo "Available presets:"
    echo "  1) Current Range (6800-7000) with nodes at 6850, 6895, 6950"
    echo "  2) Wide Range (6500-7200) with multiple levels"
    echo "  3) Clear all VP data and start fresh"
    echo ""
    read -rp "Select preset [1-3]: " PRESET

    case "$PRESET" in
        1) run_py --action preset-current ;;
        2) run_py --action preset-wide ;;
        3) run_py --action clear-vp ;;
        *) echo "Invalid preset." ;;
    esac
    pause
}

dump_vp_to_file() {
    header
    echo ""
    echo "Dump VP Data to File"
    line
    read -rp "Output file [/tmp/vp_bins.txt]: " OUTFILE
    OUTFILE="${OUTFILE:-/tmp/vp_bins.txt}"

    run_py --action dump --output "$OUTFILE"
    echo ""
    echo "Dumped to: $OUTFILE"
    pause
}

load_vp_from_file() {
    header
    echo ""
    echo "Load VP Data from File"
    line
    echo "File format: 'bucket volume' per line (bucket = price * 10)"
    echo ""
    read -rp "Input file [/tmp/vp_bins.txt]: " INFILE
    INFILE="${INFILE:-/tmp/vp_bins.txt}"

    if [[ ! -f "$INFILE" ]]; then
        echo "File not found: $INFILE"
        pause
        return
    fi

    run_py --action load --input "$INFILE"
    pause
}

###############################################
# Main Menu
###############################################
menu() {
    while true; do
        header
        echo ""
        echo "  1) Show current state (spot + VP summary)"
        echo "  2) Inject spot price"
        echo ""
        echo "  3) Inject VP range (uniform volume)"
        echo "  4) Inject VP node (high volume cluster)"
        echo "  5) Inject VP well (low volume cluster)"
        echo "  6) Apply structure preset"
        echo ""
        echo "  7) Dump VP to file"
        echo "  8) Load VP from file"
        echo ""
        echo "  x) Exit"
        echo ""
        line
        read -rp "Choice: " CH

        case "$CH" in
            1) show_current_state ;;
            2) inject_spot ;;
            3) inject_vp_range ;;
            4) inject_vp_node ;;
            5) inject_vp_well ;;
            6) inject_structure_preset ;;
            7) dump_vp_to_file ;;
            8) load_vp_from_file ;;
            x|X) echo "Goodbye."; exit 0 ;;
            *) echo "Invalid choice"; sleep 1 ;;
        esac
    done
}

###############################################
# Entry
###############################################
if [[ ! -f "$DEV_SCRIPT" ]]; then
    echo "Creating injector script at $DEV_SCRIPT..."
fi

menu
