# heartbeat.py
import asyncio
import json
import os
import time
from redis.asyncio import Redis

async def start_heartbeat(service_name: str, truth_path: str = "./root/truth.json"):
    """Start a heartbeat loop based on Truth configuration."""
    # Load Truth
    try:
        with open(truth_path, "r") as f:
            truth = json.load(f)
    except Exception as e:
        print(f"[Heartbeat:{service_name}] ⚠️ Could not load truth: {e}")
        truth = {}

    # Extract service definition
    comp = truth.get("components", {}).get(service_name, {})
    access_points = comp.get("access_points", {})

    # Find heartbeat configuration
    publish_targets = access_points.get("publish_to", [])
    heartbeat_entry = next(
        (p for p in publish_targets if "heartbeat" in p.get("key", "")), None
    )

    redis_url = (
        f"redis://{heartbeat_entry['bus']}:6379"
        if heartbeat_entry
        else os.getenv("REDIS_URL", "redis://localhost:6379")
    )
    heartbeat_key = (
        heartbeat_entry["key"]
        if heartbeat_entry
        else f"{service_name}:heartbeat"
    )

    r = Redis.from_url(redis_url, decode_responses=True)
    print(f"[Heartbeat:{service_name}] Connected to {redis_url}, key={heartbeat_key}")

    # Pulse loop
    while True:
        payload = {
            "service": service_name,
            "ts": time.time(),
            "status": "alive"
        }
        await r.publish(heartbeat_key, json.dumps(payload))
        await asyncio.sleep(10)