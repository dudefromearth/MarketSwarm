import redis
import json
import csv
from datetime import datetime

r = redis.Redis(host='127.0.0.1', port=6380, decode_responses=True)

symbols = ['SPX', 'NDX']  # Or 'I:SPX' if prefixed

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

for symbol in symbols:
    key = f"massive:heatmap:snapshot:{symbol}"
    raw = r.get(key)
    if not raw:
        print(f"No data for {symbol}")
        continue
    data = json.loads(raw)

    calls = {c['strike']: c.get('mid') for c in data.get('contracts', []) if
             c.get('type') == 'call' and c.get('mid') is not None}
    puts = {c['strike']: c.get('mid') for c in data.get('contracts', []) if
            c.get('type') == 'put' and c.get('mid') is not None}

    strikes = sorted(set(calls.keys()) | set(puts.keys()))

    filename = f"mids_{symbol}_{timestamp}.csv"
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['strike', 'call_mid', 'put_mid'])
        for s in strikes:
            writer.writerow([s, calls.get(s, ''), puts.get(s, '')])

    print(f"Saved {filename} — {len(strikes)} strikes")
    print(f"Expiration: {data.get('expiration')}, Spot: {data.get('spot')}")