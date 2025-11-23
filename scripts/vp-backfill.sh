#!/usr/bin/env bash
#
# vp-backfill.sh — Menu-driven Volume Profile historical builder for Massive
# Ernie-style admin utility (MarketSwarm standard)
#

set -euo pipefail

PY="python3"
BACKFILL_PY="services/massive/utils/build_volume_profile.py"

# ───────────────────────────────────────────────────────────
# VENV
# ───────────────────────────────────────────────────────────
if [[ -f ".venv/bin/activate" ]]; then
    source ".venv/bin/activate"
elif [[ -f "venv/bin/activate" ]]; then
    source "venv/bin/activate"
else
    echo "⚠️  No virtualenv found (.venv or venv). Using system Python."
fi


# ───────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────
function run_backfill() {
    echo ""
    echo "📦 Running Volume Profile Backfill…"
    echo "➡️  Script: ${BACKFILL_PY}"
    echo "➡️  Args:   $*"
    echo ""
    $PY "$BACKFILL_PY" "$@"
    echo ""
}

function confirm() {
    read -rp "Are you sure? (y/n): " a
    [[ "$a" == "y" || "$a" == "Y" ]]
}

function pause() {
    read -rp "Press ENTER to continue…"
}


# ───────────────────────────────────────────────────────────
# Menu Loop
# ───────────────────────────────────────────────────────────
while true; do
    clear
    echo "======================================================"
    echo "      📊 MASSIVE — Volume Profile Backfill Tool"
    echo "======================================================"
    echo ""
    echo "1) Backfill last 5 years"
    echo "2) Backfill ALL AVAILABLE Polygon history"
    echo "3) Backfill custom date range"
    echo "4) Delete + FULL rebuild (max history)"
    echo "5) Show current summary"
    echo ""
    echo "x) Exit"
    echo ""

    read -rp "> " choice

    case "$choice" in
        1)
            echo "You chose: backfill last 5 years"
            run_backfill --years 5
            pause
            ;;
        2)
            echo "You chose: FULL historical backfill"
            echo "⚠️  WARNING: This may take several minutes."
            confirm && run_backfill --years max
            pause
            ;;
        3)
            echo "Custom date range:"
            read -rp "Start date (YYYY-MM-DD): " S
            read -rp "End   date (YYYY-MM-DD): " E
            run_backfill --start "$S" --end "$E"
            pause
            ;;
        4)
            echo "⚠️  WARNING: This will delete ALL existing profile data"
            echo "and rebuild from max historical."
            confirm && run_backfill --wipe --years max
            pause
            ;;
        5)
            echo "Showing current summary…"
            run_backfill --summary
            pause
            ;;
        x|X)
            echo "Bye."
            exit 0
            ;;
        *)
            echo "Invalid option."
            pause
            ;;
    esac
done