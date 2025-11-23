#!/usr/bin/env bash
#
# vp-backfill.sh — Menu-driven Volume Profile historical builder for Massive
# Ernie-style admin utility (MarketSwarm standard)
#
# Hard-coded Polygon API Key (edit manually)
POLYGON_API_KEY="pdjraOWSpDbg3ER_RslZYe3dmn4Y7WCC"
export POLYGON_API_KEY

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
run_backfill() {
    echo ""
    echo "📦 Running Volume Profile Backfill…"
    echo "➡️  Script: ${BACKFILL_PY}"
    echo "➡️  Args:   $*"
    echo ""
    $PY "$BACKFILL_PY" "$@"
    echo ""
}

confirm() {
    read -rp "Are you sure? (y/n): " a
    [[ "$a" == "y" || "$a" == "Y" ]]
}

pause() {
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
    echo "Select ticker:"
    echo "   1) SPY → SPX"
    echo "   2) QQQ → NDX"
    echo ""
    read -rp "Choose ticker (1 or 2): " TSEL

    if [[ "$TSEL" == "1" ]]; then
        TICKER="SPY"
    elif [[ "$TSEL" == "2" ]]; then
        TICKER="QQQ"
    else
        echo "Invalid ticker selection."
        pause
        continue
    fi

    echo ""
    echo "Select publish mode (default raw):"
echo "   1) raw  (high-fidelity)"
echo "   2) tv   (TradingView-style)"
echo "   3) both"
echo ""
read -rp "Choose publish mode (1/2/3): " PMODE

if [[ "$PMODE" == "1" || -z "$PMODE" ]]; then
    PUBMODE="raw"
elif [[ "$PMODE" == "2" ]]; then
    PUBMODE="tv"
elif [[ "$PMODE" == "3" ]]; then
    PUBMODE="both"
else
    PUBMODE="raw"
fi

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
            run_backfill --ticker "$TICKER" --years 5 --publish raw
            pause
            ;;

        2)
            echo "You chose: FULL historical backfill"
            echo "⚠️  WARNING: This may take several minutes."
            if confirm; then
                run_backfill --ticker "$TICKER" --years max --publish raw
            fi
            pause
            ;;

        3)
            echo "Custom date range:"
            read -rp "Start date (YYYY-MM-DD): " S
            read -rp "End   date (YYYY-MM-DD): " E
            run_backfill --ticker "$TICKER" --start "$S" --end "$E" --publish raw
            pause
            ;;

        4)
            echo "⚠️  WARNING: This will delete ALL existing profile data"
            echo "and rebuild from max historical."
            if confirm; then
                run_backfill --ticker "$TICKER" --wipe --years max --publish raw
            fi
            pause
            ;;

        5)
            echo "Showing current summary…"
            run_backfill --ticker "$TICKER" --summary
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
