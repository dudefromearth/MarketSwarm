#!/bin/bash

# MarketSwarm - Print Strikes with Call/Put Mid Prices from Current Epoch
# Outputs CSV: Strike,Call_Mid,Put_Mid (aggregated per strike, sorted numerically)
# Default symbol I:SPX
# macOS bash 3.2 + BSD awk compatible

PORT=6380
SYMBOL="${1:-I:SPX}"

echo "Fetching call/put mid prices for $SYMBOL..."

epoch_id=$(redis-cli -p $PORT HGET "epoch:active" "$SYMBOL")
if [[ -z "$epoch_id" ]]; then
    echo "Error: No active epoch found for $SYMBOL"
    exit 1
fi

echo "Active epoch: $epoch_id"

contract_keys=$(redis-cli -p $PORT KEYS "epoch:$epoch_id:contract:*")
if [[ -z "$contract_keys" ]]; then
    echo "Error: No contracts found for epoch $epoch_id"
    exit 1
fi

# Output CSV header
echo "Strike,Call_Mid,Put_Mid"

# Temporary file for type-specific lines
tmpfile=$(mktemp)

# Process each contract: output "strike type mid"
for key in $contract_keys; do
    raw=$(redis-cli -p $PORT GET "$key")
    [[ "$raw" == "nil" || -z "$raw" ]] && continue

    type=$(echo "$raw" | jq -r '.type // empty')
    strike=$(echo "$raw" | jq -r '.strike // empty')
    mid=$(echo "$raw" | jq -r '.mid // empty')

    [[ -z "$strike" || -z "$type" || -z "$mid" || "$mid" == "null" ]] && continue

    echo "$strike $type $mid" >> "$tmpfile"
done

# Aggregate: sort by strike numeric, then process sequentially
sort -k1,1n "$tmpfile" | \
awk '
BEGIN {
    prev = ""
    c = "null"
    p = "null"
}
{
    current = $1
    if (current != prev && prev != "") {
        print prev "," c "," p
        c = "null"
        p = "null"
    }
    if ($2 == "call") c = $3
    if ($2 == "put") p = $3
    prev = current
}
END {
    if (prev != "") print prev "," c "," p
}'

# Cleanup
rm -f "$tmpfile"