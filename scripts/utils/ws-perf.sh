#!/bin/bash
# ws-perf.sh — View WS pipeline performance analytics
#
# Usage: ./ws-perf.sh [--watch]

REDIS_CLI="redis-cli -p 6380"

show_analytics() {
    echo "=== WS Worker Analytics ==="
    $REDIS_CLI HGETALL massive:ws:analytics | paste - - | column -t
    echo ""

    echo "=== WS Consumer Analytics ==="
    $REDIS_CLI HGETALL massive:ws:consumer:analytics | paste - - | column -t
    echo ""

    echo "=== WS Hydrate Analytics ==="
    $REDIS_CLI HGETALL massive:ws:hydrate:analytics | paste - - | column -t

    # Calculate avg diffs per emit
    diffs_total=$($REDIS_CLI HGET massive:ws:hydrate:analytics diffs_total 2>/dev/null)
    emits_total=$($REDIS_CLI HGET massive:ws:hydrate:analytics emits_total 2>/dev/null)
    if [ -n "$diffs_total" ] && [ -n "$emits_total" ] && [ "$emits_total" -gt 0 ]; then
        avg=$(echo "scale=2; $diffs_total / $emits_total" | bc)
        echo ""
        echo "  >> Avg diffs/emit: $avg  (total: $diffs_total diffs over $emits_total emits)"
    fi
    echo ""

    echo "=== Snapshot Analytics ==="
    $REDIS_CLI HGETALL massive:snapshot:analytics | paste - - | column -t
    echo ""

    echo "=== Chain Analytics ==="
    $REDIS_CLI HGETALL massive:chain:analytics | paste - - | column -t
    echo ""

    echo "=== Stream Info ==="
    echo -n "Stream length: "
    $REDIS_CLI XLEN massive:ws:stream
    echo -n "Subscription count: "
    $REDIS_CLI SCARD massive:ws:subscription_list
    echo -n "Emit stream length: "
    $REDIS_CLI XLEN massive:ws:emit:stream
    echo -n "Strike stream (SPX): "
    $REDIS_CLI XLEN massive:ws:strike:stream:I:SPX
    echo -n "Strike stream (NDX): "
    $REDIS_CLI XLEN massive:ws:strike:stream:I:NDX
    echo ""

    echo "=== Hot Strikes (SPX) ==="
    $REDIS_CLI HGETALL massive:ws:strike:hot:I:SPX 2>/dev/null | head -20
}

if [ "$1" == "--watch" ]; then
    watch -n 1 "$0"
else
    show_analytics
fi
