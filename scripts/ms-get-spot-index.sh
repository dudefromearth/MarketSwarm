#!/bin/bash
#
# get-spot-index.sh — Menu wrapper for get_index_spot.py
#

# Resolve repo root based on this script’s location
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Path to the Python utility
GET_INDEX_SPOT="$REPO_ROOT/services/massive/utils/get_index_spot.py"

# Verify the Python script exists
if [[ ! -f "$GET_INDEX_SPOT" ]]; then
    echo "ERROR: get_index_spot.py not found at: $GET_INDEX_SPOT"
    exit 1
fi

API_KEY="${MASSIVE_API_KEY:-pdjraOWSpDbg3ER_RslZYe3dmn4Y7WCC}"

run_spot() {
    local SYMBOL=$1
    local MODE=$2

    echo ""
    echo "------------------------------------------------------------"
    echo " Retrieving spot for: $SYMBOL"
    echo " Mode: $MODE"
    echo "------------------------------------------------------------"

    RESULT=$(python3 "$GET_INDEX_SPOT" "$SYMBOL" --mode="$MODE" 2>&1)

    # Detect errors but do not crash
    if echo "$RESULT" | grep -qi "error"; then
        echo "⚠  ERROR:"
        echo "$RESULT"
        echo "------------------------------------------------------------"
        return
    fi

    echo "$RESULT"
    echo "------------------------------------------------------------"
}

while true; do
    clear
    echo "=== MarketSwarm Index Spot Tool ==="
    echo ""
    echo "API Key in use: $API_KEY"
    echo ""
    echo "1) Get spot for I:SPX"
    echo "2) Get spot for I:NDX"
    echo "3) Get spot for I:VIX"
    echo "4) Enter custom index (I:XXXX)"
    echo "5) Exit"
    echo ""
    read -p "Select an option: " CHOICE

    case "$CHOICE" in
        1) SYMBOL="I:SPX" ;;
        2) SYMBOL="I:NDX" ;;
        3) SYMBOL="I:VIX" ;;
        4)
            read -p "Enter index symbol (e.g. I:RTY): " SYMBOL
            if [[ -z "$SYMBOL" ]]; then
                echo "Invalid symbol."
                read -p "Press Enter to continue..."
                continue
            fi
            ;;
        5)
            echo "Goodbye."
            exit 0
            ;;
        *)
            echo "Invalid choice."
            read -p "Press Enter to continue..."
            continue
            ;;
    esac

    # Ask for mode
    echo ""
    echo "Select output mode:"
    echo "   1) spot (numeric only)"
    echo "   2) json (raw)"
    echo "   3) pretty (formatted)"
    echo ""
    read -p "Mode: " MODE_CHOICE

    case "$MODE_CHOICE" in
        1) MODE="spot" ;;
        2) MODE="json" ;;
        3) MODE="pretty" ;;
        *)
            echo "Invalid mode."
            read -p "Press Enter to continue..."
            continue
            ;;
    esac

    run_spot "$SYMBOL" "$MODE"
    read -p "Press Enter to continue..."
done