#!/bin/bash

# MarketSwarm Massive - Builder Analytics Menu
# Path: services/massive/intel/utils/builder_analytics.py

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_PATH="$REPO_ROOT/services/massive/intel/utils/builder_analytics.py"

if [[ ! -f "$SCRIPT_PATH" ]]; then
    echo "Error: builder_analytics.py not found at $SCRIPT_PATH"
    exit 1
fi

VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
if [[ -f "$VENV_PYTHON" ]]; then
    PYTHON="$VENV_PYTHON"
else
    PYTHON="python3"
fi

while true; do
    clear
    echo "=========================================="
    echo "  Massive Model Builders Analytics Tool  "
    echo "=========================================="
    echo
    echo "1) View current analytics (terminal + chart)"
    echo "2) Export analytics to JSON file"
    echo "3) View + export + chart"
    echo "4) Exit"
    echo
    read -p "Choose an option [1-4]: " choice

    case $choice in
        1)
            echo "Fetching analytics..."
            $PYTHON "$SCRIPT_PATH"
            echo "Chart saved as model_analytics_dashboard.png"
            read -p "Press Enter to continue..."
            ;;
        2)
            timestamp=$(date +"%Y%m%d_%H%M%S")
            outfile="builder_analytics_$timestamp.json"
            echo "Fetching and saving to $outfile..."
            $PYTHON "$SCRIPT_PATH" --output json --file "$outfile"
            echo "Saved to $outfile"
            read -p "Press Enter to continue..."
            ;;
        3)
            timestamp=$(date +"%Y%m%d_%H%M%S")
            outfile="builder_analytics_$timestamp.json"
            echo "Fetching analytics..."
            $PYTHON "$SCRIPT_PATH"
            $PYTHON "$SCRIPT_PATH" --output json --file "$outfile"
            echo "Chart saved as model_analytics_dashboard.png"
            echo "Saved to $outfile"
            read -p "Press Enter to continue..."
            ;;
        4)
            echo "Goodbye!"
            exit 0
            ;;
        *)
            echo "Invalid option. Please try again."
            sleep 1
            ;;
    esac
done