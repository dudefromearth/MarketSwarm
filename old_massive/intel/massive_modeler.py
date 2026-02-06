#!/usr/bin/env python3
"""
massive_modeler.py — fan-out chain snapshots into models.

- Consumes from Redis stream 'massive:chain-feed'
- For each entry, load the chain snapshot hash
- Compute models (gex, heatmap, etc.)
- Write to massive:model:* keys
"""

import json
import os
import time
import redis
from datetime import datetime, timezone

STREAM_KEY = "massive:chain-feed"
GROUP_NAME = "massive_modelers"
CONSUMER_NAME = os.getenv("HOSTNAME", "modeler-1")

def log(stage, emoji, msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}][modeler|{stage}]{emoji} {msg}")

def make_redis_client():
    url = os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380")
    return redis.Redis.from_url(url, decode_responses=True)

def ensure_group(r):
    try:
        r.xgroup_create(STREAM_KEY, GROUP_NAME, id="$", mkstream=True)
        log("init", "✨", f"Created group {GROUP_NAME} on {STREAM_KEY}")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            # already exists
            pass
        else:
            raise

# ---- stub model computations ----

def compute_gex(chain):
    # TODO: real implementation; stub for now
    return {"gex": 123.45}

def compute_heatmap(chain):
    return {"heatmap": "stub"}

def compute_market_mode(chain):
    return {"mode": "neutral"}

def compute_volume_profile(chain):
    return {"vp": "stub"}

def process_entry(r, entry_id, fields):
    symbol = fields["symbol"]
    snapshot_key = fields["snapshot_key"]
    snapshot_ts = fields.get("snapshot_ts")

    # Load chain snapshot
    data = r.hgetall(snapshot_key)
    if not data:
        log("process", "⚠️", f"No snapshot for {snapshot_key}, skipping")
        return

    chain_json = data.get("chain_json")
    if not chain_json:
        log("process", "⚠️", f"No chain_json in {snapshot_key}, skipping")
        return

    chain = json.loads(chain_json)

    # Compute models
    gex = compute_gex(chain)
    heatmap = compute_heatmap(chain)
    mode = compute_market_mode(chain)
    vp = compute_volume_profile(chain)

    # Write to model keys (per symbol; time-aware or latest)
    # Example: latest-per-symbol hashes
    r.hset("massive:model:gex",         mapping={symbol: json.dumps(gex)})
    r.hset("massive:model:heatmap",     mapping={symbol: json.dumps(heatmap)})
    r.hset("massive:model:market_mode", mapping={symbol: json.dumps(mode)})
    r.hset("massive:model:volume_profile", mapping={symbol: json.dumps(vp)})

    # Optionally, time-keyed model snapshots as well:
    # model_key = f"massive:model:gex:{symbol}:{snapshot_ts}"
    # r.hset(model_key, mapping=gex)

    log("process", "✅", f"Processed {symbol} @ {snapshot_ts} ({entry_id})")

def main():
    r = make_redis_client()
    ensure_group(r)

    log("main", "🚀", "Massive modeler starting…")

    while True:
        resp = r.xreadgroup(
            GROUP_NAME,
            CONSUMER_NAME,
            {STREAM_KEY: ">"},
            count=10,
            block=5000,
        )

        if not resp:
            continue

        for stream, entries in resp:
            for entry_id, fields in entries:
                try:
                    process_entry(r, entry_id, fields)
                    # Acknowledge
                    r.xack(STREAM_KEY, GROUP_NAME, entry_id)
                except Exception as e:
                    log("main", "❌", f"Error processing {entry_id}: {e}")

        time.sleep(0.01)

if __name__ == "__main__":
    main()