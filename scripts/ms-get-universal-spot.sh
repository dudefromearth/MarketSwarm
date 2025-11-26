#!/bin/bash
#
# ms-get-universal-spot.sh — Full Universal Snapshot Menu Tool
#
# Uses Massive RESTClient and list_universal_snapshots()
# Works with ANY symbol:
#   • I:SPX, I:NDX, SPY, QQQ
#   • Stocks, crypto, FX, options, etc.
#

# Resolve repo root based on script's own location
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Correct Python script path
PYFILE="$REPO_ROOT/services/massive/utils/get_universal_spot.py"

API_KEY="${MASSIVE_API_KEY:-pdjraOWSpDbg3ER_RslZYe3dmn4Y7WCC}"

# Validate Python file
if [[ ! -f "$PYFILE" ]]; then
    echo "ERROR: get-universal-spot.py not found at:"
    echo "       $PYFILE"
    exit 1
fi


run_query() {
    local SYMBOL=$1

    echo ""
    echo "------------------------------------------------------------"
    echo " Requesting universal snapshot for: $SYMBOL"
    echo "------------------------------------------------------------"

    RESULT=$(python "$PYFILE" "$SYMBOL" 2>&1)

    if echo "$RESULT" | grep -qi "ERROR"; then
        echo "⚠ ERROR:"
        echo "$RESULT"
    else
        echo "$RESULT"
    fi

    echo "------------------------------------------------------------"
    echo ""
}


while true; do
    clear
    echo "=== MarketSwarm Universal Snapshot Tool ==="
    echo "API Key: $API_KEY"
    echo ""
    echo "1) I:SPX"
    echo "2) I:NDX"
    echo "3) SPY"
    echo "4) QQQ"
    echo "5) Enter ANY custom ticker"
    echo "6) Exit"
    echo ""
    read -p "Select: " CHOICE

    case "$CHOICE" in
        1) run_query "I:SPX"; read -p "Press Enter..." ;;
        2) run_query "I:NDX"; read -p "Press Enter..." ;;
        3) run_query "SPY"; read -p "Press Enter..." ;;
        4) run_query "QQQ"; read -p "Press Enter..." ;;
        5)
            read -p "Enter ticker: " CUSTOM
            if [[ -n "$CUSTOM" ]]; then
                run_query "$CUSTOM"
            else
                echo "No ticker entered."
            fi
            read -p "Press Enter..."
            ;;
        6)
            echo "Goodbye."
            exit 0
            ;;
        *)
            echo "Invalid option."
            read -p "Press Enter..."
            ;;
    esac
done