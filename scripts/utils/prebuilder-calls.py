#!/usr/bin/env python3
import redis
import json
import csv
from datetime import datetime

r = redis.Redis(host='127.0.0.1', port=6380, decode_responses=True)

symbol = 'I:SPX'
key = f"massive:heatmap:snapshot:{symbol}"
raw = r.get(key)

if not raw:
    print("Error: No heatmap snapshot for I:SPX")
    exit(1)

data = json.loads(raw)
print(f"Snapshot ts: {data.get('ts')}, epoch: {data.get('epoch')}")

contracts = data.get('contracts', [])
calls = {}
for c in contracts:
    if c.get('type') == 'call':
        strike = c.get('strike')
        mid = c.get('mid')
        if strike is not None and mid is not None and mid != 0:
            calls[float(strike)] = float(mid)

if not calls:
    print("Error: No valid calls in snapshot")
    exit(1)

sorted_strikes = sorted(calls.keys(), reverse=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"snapshot_calls_{timestamp}.csv"

with open(filename, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Strike', 'Mid'])
    for s in sorted_strikes:
        writer.writerow([s, calls[s]])

print(f"CSV saved: {filename} ({len(sorted_strikes)} strikes) from snapshot contracts")