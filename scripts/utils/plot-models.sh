#!/bin/bash

# MarketSwarm - Heatmap & GEX Plot Tool
# Interactive menu to plot heatmap + GEX side-by-side
# Supports: butterfly, vertical, single strategies
# Filters: symbol, strategy, side (call/put), DTE

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_PATH="$REPO_ROOT/services/massive/intel/utils/heatmap_gex_plot.py"

if [[ ! -f "$SCRIPT_PATH" ]]; then
    echo "Error: heatmap_gex_plot.py not found at $SCRIPT_PATH"
    exit 1
fi

VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
if [[ -f "$VENV_PYTHON" ]]; then
    PYTHON="$VENV_PYTHON"
else
    PYTHON="python3"
fi

REDIS_PORT=6380  # adjust if needed

# Default values
DEFAULT_SYMBOL="I:SPX"
DEFAULT_STRATEGY="butterfly"
DEFAULT_SIDE="call"
DEFAULT_MODE="live"
DEFAULT_DTE="0"

# Current values
symbol="$DEFAULT_SYMBOL"
strategy="$DEFAULT_STRATEGY"
side="$DEFAULT_SIDE"
mode="$DEFAULT_MODE"
dte="$DEFAULT_DTE"

pause() {
  echo
  read -rp "Press ENTER to continue..."
}

while true; do
    clear
    echo "=========================================="
    echo "  Heatmap & GEX Plot Tool"
    echo "=========================================="
    echo
    echo "Current selection:"
    echo "  Symbol   : $symbol"
    echo "  Strategy : $strategy"
    if [[ "$strategy" == "single" ]]; then
        echo "  Side     : both (call & put)"
    else
        echo "  Side     : $side"
    fi
    echo "  DTE      : $dte"
    echo "  Mode     : $mode (live or replay)"
    echo
    echo "1) Change Symbol   (current: $symbol)"
    echo "2) Change Strategy (current: $strategy)"
    if [[ "$strategy" != "single" ]]; then
        echo "3) Change Side     (current: $side)"
    else
        echo "3) [N/A for single strategy]"
    fi
    echo "4) Change DTE      (current: $dte)"
    echo "5) Change Mode     (current: $mode)"
    echo "6) Generate Plot"
    echo "7) List available DTEs"
    echo "8) Reset to defaults"
    echo "9) Exit"
    echo
    read -p "Choose an option [1-9]: " choice

    case $choice in
        1)
            echo "Available symbols: I:SPX, I:NDX"
            read -p "Enter symbol: " input_symbol
            symbol=${input_symbol:-$symbol}
            ;;
        2)
            echo "Available strategies:"
            echo "  butterfly - Long wings, short 2x center"
            echo "  vertical  - Debit spread (bull call / bear put)"
            echo "  single    - Individual option prices"
            read -p "Enter strategy: " input_strategy
            strategy=${input_strategy:-$strategy}
            ;;
        3)
            if [[ "$strategy" != "single" ]]; then
                echo "Available sides: call, put"
                read -p "Enter side: " input_side
                side=${input_side:-$side}
            else
                echo "Side selection not applicable for 'single' strategy (shows both)."
                sleep 2
            fi
            ;;
        4)
            echo "Enter DTE (days to expiration):"
            echo "  0 = 0-DTE (today's expiry)"
            echo "  1 = 1-DTE (tomorrow's expiry)"
            echo "  etc."
            read -p "Enter DTE: " input_dte
            dte=${input_dte:-$dte}
            ;;
        5)
            echo "Available modes: live, replay"
            read -p "Enter mode: " input_mode
            mode=${input_mode:-$mode}
            ;;
        6)
            echo "Generating plot..."
            echo "  Symbol   : $symbol"
            echo "  Strategy : $strategy"
            if [[ "$strategy" != "single" ]]; then
                echo "  Side     : $side"
            else
                echo "  Side     : both (call & put)"
            fi
            echo "  DTE      : $dte"
            echo "  Mode     : $mode"
            echo "----------------------------------------"

            source "$REPO_ROOT/.venv/bin/activate"

            # Fetch model JSON from Redis based on mode
            if [[ "$mode" == "replay" ]]; then
                raw_model=$(redis-cli -p $REDIS_PORT XREVRANGE "massive:heatmap:replay:$symbol" + - COUNT 1 | grep payload | awk '{$1=""; print $0}' | sed 's/^"//;s/"$//')
            else
                raw_model=$(redis-cli -p $REDIS_PORT GET "massive:heatmap:model:$symbol:latest")
            fi

            if [[ -z "$raw_model" ]]; then
                echo "Error: No model data found in Redis for $symbol ($mode mode)"
                deactivate
                pause
                continue
            fi

            # Save to temp file for plot script
            temp_file="/tmp/massive_model_$symbol.json"
            echo "$raw_model" > "$temp_file"

            if [[ "$strategy" == "single" ]]; then
                $PYTHON "$SCRIPT_PATH" --symbol "$symbol" --strategy "$strategy" --dte "$dte" --input "$temp_file"
            else
                $PYTHON "$SCRIPT_PATH" --symbol "$symbol" --strategy "$strategy" --side "$side" --dte "$dte" --input "$temp_file"
            fi

            deactivate

            rm -f "$temp_file"

            echo "----------------------------------------"
            echo "Plot saved as heatmap_gex_*.png (timestamped)"
            pause
            ;;
        7)
            echo "Fetching available DTEs for $symbol..."
            source "$REPO_ROOT/.venv/bin/activate"
            redis-cli -p $REDIS_PORT GET "massive:heatmap:model:$symbol:latest" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    dtes = data.get('dtes_available', [])
    counts = data.get('dte_tile_counts', {})
    print('Available DTEs:')
    for d in dtes:
        count = counts.get(str(d), 0)
        print(f'  DTE {d}: {count} tiles')
except:
    print('Error reading model data')
"
            deactivate
            pause
            ;;
        8)
            symbol="$DEFAULT_SYMBOL"
            strategy="$DEFAULT_STRATEGY"
            side="$DEFAULT_SIDE"
            mode="$DEFAULT_MODE"
            dte="$DEFAULT_DTE"
            echo "Reset to defaults."
            sleep 1
            ;;
        9)
            echo "Goodbye!"
            exit 0
            ;;
        *)
            echo "Invalid option."
            sleep 1
            ;;
    esac
done