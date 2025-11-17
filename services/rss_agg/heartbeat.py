# heartbeat.py
import asyncio
import time
import json
from redis.asyncio import Redis


async def start_heartbeat(service_name: str, truth: dict):
    """Send heartbeat pulses based on canonical truth.json."""

    comp = truth.get("components", {}).get(service_name)
    if not comp:
        raise RuntimeError(f"No component entry in truth for {service_name}")

    hb = comp.get("heartbeat", {})
    interval = hb.get("interval_sec", 5)
    channel = hb.get("channel", f"{service_name}:heartbeat")

    # Lookup bus target from access_points.publish_to
    publish_to = comp.get("access_points", {}).get("publish_to", [])
    hb_target = next(
        (p for p in publish_to if p.get("key") == channel),
        None
    )

    if not hb_target:
        raise RuntimeError(f"No heartbeat publish_to entry for {service_name}")

    bus_name = hb_target["bus"]

    # Resolve Redis host/port for this bus
    bus_cfg = truth.get("buses", {}).get(bus_name)
    if not bus_cfg:
        raise RuntimeError(f"Bus '{bus_name}' not defined in truth")

    # redis://127.0.0.1:6379
    redis_url = bus_cfg["url"]

    r = Redis.from_url(redis_url, decode_responses=True)
    print(f"[Heartbeat:{service_name}] Connected to {redis_url}, channel={channel}")

    # Pulse loop
    while True:
        payload = {
            "service": service_name,
            "ts": time.time(),
            "status": "alive"
        }
        await r.publish(channel, json.dumps(payload))
        print(f"[Heartbeat:{service_name}] ✔ pulse → {channel}")
        await asyncio.sleep(interval)