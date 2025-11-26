#!/bin/bash
#
# chain_loader.sh — MarketSwarm Admin Menu
# -------------------------------------------------------
# Interactive menu for:
#   - Configuring chain load parameters
#   - Running startup_chain_loader.py
#   - Inspecting Redis contract counts
#   - Cleaning chain keys
#   - Testing loader behavior
#
# Defaults:
#   STRIKE_WINDOW=30  (±30 strikes)
#   MAX_DTE=5
#
# -------------------------------------------------------

# Default config
STRIKE_WINDOW=30
MAX_DTE=5
PYTHON_LOADER="services/massive/intel/startup_chain_loader.py"
REDIS_PORT=6380

clear

# Function: show header
show_header() {
    echo "============================================================"
    echo "      MarketSwarm Options Chain Loader — Admin Console"
    echo "============================================================"
}

# Function: modify STRIKE_WINDOW
set_strike_window() {
    echo -n "Enter new strike window (default 30): "
    read NEW_WIN
    if [[ ! -z "$NEW_WIN" ]]; then
        STRIKE_WINDOW=$NEW_WIN
    fi
    echo "Strike window set to ±$STRIKE_WINDOW strikes."
}

# Function: modify MAX_DTE
set_max_dte() {
    echo -n "Enter new max DTE (default 5): "
    read NEW_DTE
    if [[ ! -z "$NEW_DTE" ]]; then
        MAX_DTE=$NEW_DTE
    fi
    echo "Max DTE set to $MAX_DTE."
}

# Function: run loader
run_loader() {
    show_header
    echo "🚀 Running chain loader..."
    echo "Config:"
    echo "  • Strike Window: ±$STRIKE_WINDOW"
    echo "  • Max DTE:       $MAX_DTE"
    echo "------------------------------------------------------------"

    STRIKE_WINDOW=$STRIKE_WINDOW MAX_DTE=$MAX_DTE \
        python3 "$PYTHON_LOADER"

    echo "------------------------------------------------------------"
    echo "Loader finished. Press Enter to continue."
    read
}

# Function: view redis stats
redis_stats() {
    show_header
    echo "📊 Redis Stats — chain:* counts"
    echo "------------------------------------------------------------"
    redis-cli -p $REDIS_PORT KEYS "chain:*" | wc -l
    echo "contracts stored"
    echo "------------------------------------------------------------"
    echo "Press Enter to continue."
    read
}

# Function: inspect per-symbol keys
symbol_stats() {
    show_header
    echo "📊 Redis Stats by Symbol"
    echo "------------------------------------------------------------"
    for sym in SPX SPY NDX QQQ; do
        COUNT=$(redis-cli -p $REDIS_PORT KEYS "chain:${sym}:*" | wc -l)
        echo "  ${sym}: ${COUNT} contracts"
    done
    echo "------------------------------------------------------------"
    read -p "Press Enter to continue."
}

# Function: clean chain:* keys
clear_chain_keys() {
    show_header
    echo "🧹 Removing chain:* keys ..."
    redis-cli -p $REDIS_PORT KEYS "chain:*" | xargs redis-cli -p $REDIS_PORT DEL > /dev/null 2>&1
    echo "Done."
    read -p "Press Enter to continue."
}

# MENU LOOP
while true; do
    show_header
    echo "Current Config:"
    echo "  • Strike Window: ±$STRIKE_WINDOW"
    echo "  • Max DTE:       $MAX_DTE"
    echo "------------------------------------------------------------"
    echo "1) Run Full Chain Loader"
    echo "2) Change Strike Window"
    echo "3) Change Max DTE"
    echo "4) Redis — Total Contract Count"
    echo "5) Redis — Contract Count by Symbol"
    echo "6) Delete All chain:* Keys"
    echo "7) Quit"
    echo "------------------------------------------------------------"
    echo -n "Select an option: "
    read CHOICE

    case $CHOICE in
        1) run_loader ;;
        2) set_strike_window ;;
        3) set_max_dte ;;
        4) redis_stats ;;
        5) symbol_stats ;;
        6) clear_chain_keys ;;
        7) clear ; exit 0 ;;
        *) echo "Invalid option"; sleep 1 ;;
    esac
done