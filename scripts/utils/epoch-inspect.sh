#!/usr/bin/env bash

REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6380}"
REDIS="redis-cli -u $REDIS_URL"

NOW=$(date +%s)

echo ""
printf "%-6s %-28s %-7s %-6s %-8s %-8s %-4s %-8s %-6s\n" \
  "SYMBOL" "EPOCH_ID" "AGE(s)" "DIRTY" "DORMANT" "FORCED" "WS" "HEATMAP" "GEX"

echo "------------------------------------------------------------------------------------------------"

SYMBOLS=$($REDIS hkeys epoch:active 2>/dev/null)

for SYMBOL in $SYMBOLS; do
  EPOCH=$($REDIS hget epoch:active "$SYMBOL")
  META_KEY="epoch:meta:$EPOCH"

  CREATED=$($REDIS hget "$META_KEY" created_ts)
  STRIKE_COUNT=$($REDIS hget "$META_KEY" strike_count)
  FORCED=$($REDIS hget "$META_KEY" forced_dirty)
  DORMANT=$($REDIS hget "$META_KEY" dormant_count)

  HAD_WS=$($REDIS get "epoch:$EPOCH:had_ws_updates")

  AGE="?"
  if [[ -n "$CREATED" ]]; then
    AGE=$(printf "%.0f" "$(echo "$NOW - $CREATED" | bc)")
  fi

  DIRTY="no"
  $REDIS sismember epoch:dirty "$EPOCH" | grep -q 1 && DIRTY="yes"

  CLEAN="no"
  $REDIS sismember epoch:clean "$EPOCH" | grep -q 1 && CLEAN="yes"

  WS="no"
  [[ "$HAD_WS" == "1" ]] && WS="yes"

  # Heatmap contract count (latest snapshot)
  HEATMAP_KEY="massive:heatmap:snapshot:$SYMBOL"
  HEATMAP_COUNT=$($REDIS get "$HEATMAP_KEY" | jq -r '.contract_count' 2>/dev/null)
  [[ "$HEATMAP_COUNT" == "null" ]] && HEATMAP_COUNT="0"

  # GEX levels (latest model)
  GEX_KEY="massive:gex:model:$SYMBOL"
  GEX_LEVELS=$($REDIS get "$GEX_KEY" | jq '.levels | length' 2>/dev/null)
  [[ "$GEX_LEVELS" == "null" ]] && GEX_LEVELS="0"

  printf "%-6s %-28s %-7s %-6s %-8s %-8s %-4s %-8s %-6s\n" \
    "$SYMBOL" "$EPOCH" "$AGE" "$DIRTY" "$DORMANT" "$FORCED" "$WS" "$HEATMAP_COUNT" "$GEX_LEVELS"
done

echo ""