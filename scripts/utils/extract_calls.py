#!/usr/bin/env python3
import redis
import json
import csv
from datetime import datetime

r = redis.Redis(host='127.0.0.1', port=6380, decode_responses=True)

symbol = 'I:SPX'
epoch_id = r.hget('epoch:active', symbol)

if not epoch_id:
    print("Error: No active epoch for I:SPX")
    exit(1)

print(f"Active epoch: {epoch_id}")

contract_keys = r.keys(f"epoch:{epoch_id}:contract:*")

calls = {}
for key in contract_keys:
    raw = r.get(key)
    if raw:
        try:
            data = json.loads(raw)
            if data.get('type') == 'call':
                strike = data.get('strike')
                mid = data.get('mid')
                if strike is not None and mid is not None and mid != 0:
                    calls[float(strike)] = float(mid)
        except (json.JSONDecodeError, ValueError):
            continue

if not calls:
    print("Error: No valid call contracts found")
    exit(1)

# Sort strikes descending (matches plot Y-axis)
sorted_strikes = sorted(calls.keys(), reverse=True)

# Timestamped CSV
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"spx_calls_{timestamp}.csv"

with open(filename, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Strike', 'Mid'])
    for s in sorted_strikes:
        writer.writerow([s, calls[s]])

print(f"CSV saved: {filename} ({len(sorted_strikes)} strikes)")
print("Paste into Excel A1 for butterfly verification.")