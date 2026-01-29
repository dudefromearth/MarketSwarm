#!/bin/bash

# redis_explorer.sh - Full menu-driven explorer for Massive Redis (port 6380)

PORT=6380
REDIS="redis-cli -p $PORT"

clear
echo "=== MarketSwarm Redis Explorer (port $PORT) ==="
echo

while true; do
    echo "1) Quick Status (memory + key count)"
    echo "2) Full Memory Details"
    echo "3) Key Counts & Ratios (incl. heatmap vs epochs)"
    echo "4) Top 20 Keys by Memory Usage"
    echo "5) Live Memory Monitor (single line, no scroll)"
    echo "6) Pipeline Performance ENV Status"
    echo "7) Exit"
    echo
    read -p "Choose [1-7]: " choice
    echo

    case $choice in
        1)
            echo "=== Quick Status ==="
            $REDIS INFO memory | grep -E "used_memory_human|used_memory_dataset_human|used_memory_peak_human|mem_fragmentation_ratio"
            echo "Total keys: $($REDIS DBSIZE)"
            ;;
        2)
            echo "=== Full Memory Details ==="
            $REDIS INFO memory
            ;;
        3)
            echo "=== Key Counts & Ratios ==="
            TOTAL_KEYS=$($REDIS DBSIZE)
            MASSIVE_COUNT=$($REDIS KEYS "massive:*" | wc -l | tr -d ' ')
            EPOCH_COUNT=$($REDIS KEYS "epoch:*" | wc -l | tr -d ' ')
            EPOCH_CONTRACT_COUNT=$($REDIS KEYS "epoch:*contract:*" | wc -l | tr -d ' ')
            HEATMAP_MODEL_COUNT=$($REDIS KEYS "massive:heatmap:model:*" | wc -l | tr -d ' ')
            HEATMAP_SNAPSHOT_COUNT=$($REDIS KEYS "massive:heatmap:snapshot:*" | wc -l | tr -d ' ')

            echo "Total Redis keys                 : $TOTAL_KEYS"
            echo "massive:* keys                   : $MASSIVE_COUNT"
            echo "epoch:* keys                     : $EPOCH_COUNT"
            echo "epoch:*contract:* keys           : $EPOCH_CONTRACT_COUNT"
            echo "heatmap models                   : $HEATMAP_MODEL_COUNT"
            echo "heatmap snapshots                : $HEATMAP_SNAPSHOT_COUNT"

            if [[ $EPOCH_COUNT -gt 0 ]]; then
                MODEL_RATIO=$(awk "BEGIN {printf \"%.2f\", $HEATMAP_MODEL_COUNT / $EPOCH_COUNT}")
                SNAP_RATIO=$(awk "BEGIN {printf \"%.2f\", $HEATMAP_SNAPSHOT_COUNT / $EPOCH_COUNT}")
                echo "Heatmap models per epoch         : $MODEL_RATIO"
                echo "Heatmap snapshots per epoch      : $SNAP_RATIO"
            else
                echo "Ratios                           : N/A (no epochs yet)"
            fi
            ;;
        4)
            echo "=== Top 20 Keys by Memory Usage ==="
            echo "(Scanning all keys — this may take 10-30 seconds on large DB)"
            echo
            $REDIS --scan | while read key; do
                [[ -z "$key" ]] && continue
                size=$($REDIS MEMORY USAGE "$key" 2>/dev/null || echo 0)
                printf "%s %s\n" "$size" "$key"
            done | sort -nr | head -20 | awk '{printf "%10s bytes: %s\n", $1, $2}'
            ;;
        5)
            echo "=== Live Memory Monitor (single line, no scroll) ==="
            echo "Press Ctrl+C to return to menu"
            echo
            trap 'printf "\n"; echo "Back to menu..."; break' INT
            while true; do
                INFO=$($REDIS --raw INFO memory 2>/dev/null)
                if [[ -z "$INFO" ]]; then
                    LINE="ERROR: redis-cli failed"
                else
                    DATASET=$(echo "$INFO" | awk -F: '/used_memory_dataset_human/ {print $2}' | tr -d ' \r')
                    TOTAL=$(echo "$INFO" | awk -F: '/used_memory_human/ {print $2}' | tr -d ' \r')
                    PEAK=$(echo "$INFO" | awk -F: '/used_memory_peak_human/ {print $2}' | tr -d ' \r')
                    FRAG=$(echo "$INFO" | awk -F: '/mem_fragmentation_ratio/ {print $2}' | tr -d ' \r')
                    LINE="Dataset: ${DATASET:-N/A} | Total: ${TOTAL:-N/A} | Peak: ${PEAK:-N/A} | Frag: ${FRAG:-N/A}"
                fi
                printf "\r\033[K%s" "$LINE"   # Clear line fully
                sleep 2
            done
            trap - INT  # Clean up trap
            ;;
        6)
            echo "=== Pipeline Performance ENV Status ==="
            echo "(From truth.json stored in Redis — defaults if missing)"
            echo

            TRUTH_REDIS="redis-cli -p 6379"
            RAW_TRUTH=$($TRUTH_REDIS GET truth 2>/dev/null)

            if [[ -z "$RAW_TRUTH" ]]; then
                echo "Error: No 'truth' key found on port 6379"
            else
                echo "WS Hydration Max DTE     : $(echo "$RAW_TRUTH" | jq -r '.components.massive.env.MASSIVE_WS_HYDRATE_MAX_DTE // "5"')"
                echo "Heatmap Max DTE          : $(echo "$RAW_TRUTH" | jq -r '.components.massive.env.MASSIVE_HEATMAP_MAX_DTE // "10"')"
                echo "Chain Interval (sec)     : $(echo "$RAW_TRUTH" | jq -r '.components.massive.env.MASSIVE_CHAIN_INTERVAL_SEC // "30"')"
                echo "Chain Num Expirations    : $(echo "$RAW_TRUTH" | jq -r '.components.massive.env.MASSIVE_CHAIN_NUM_EXPIRATIONS // "5"')"
                echo "WS Reconnect Delay (sec) : $(echo "$RAW_TRUTH" | jq -r '.components.massive.env.MASSIVE_WS_RECONNECT_DELAY_SEC // "5.0"')"
                echo "Debug Mode               : $(echo "$RAW_TRUTH" | jq -r '.components.massive.env.DEBUG_MASSIVE // "false"')"
            fi
            ;;
        7)
            echo "Goodbye!"
            exit 0
            ;;
        *)
            echo "Invalid choice — try again."
            ;;
    esac

    echo
    read -p "Press Enter to continue..."
    clear
done