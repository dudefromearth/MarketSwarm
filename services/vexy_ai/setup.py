#!/usr/bin/env python3
"""
vexy_ai/setup.py

Generic MarketSwarm service setup pattern, specialized for vexy_ai.

Responsibilities:
- Load Truth from system-redis (key: "truth")
- Locate this service's component block: truth["components"]["vexy_ai"]
- Resolve bus URLs from truth["buses"]
- Build normalized I/O endpoints (inputs/outputs) with redis_url attached
- Expose heartbeat config
- Return a config dict consumed by main.py and orchestrator.py
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict
from urllib.parse import urlparse

from redis import Redis

import logutil  # services/vexy_ai/logutil.py


SERVICE_NAME = "vexy_ai"
TRUTH_KEY = "truth"


def _redis_from_url(url: str) -> Redis:
    parsed = urlparse(url or "redis://127.0.0.1:6379")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6379
    return Redis(host=host, port=port, decode_responses=True)


def _load_truth(r: Redis, service_name: str) -> Dict[str, Any]:
    """Load the canonical Truth doc from system-redis."""
    logutil.log(service_name, "INFO", "📖", f"Loading Truth from Redis (key={TRUTH_KEY})")
    raw = r.get(TRUTH_KEY)
    if not raw:
        raise RuntimeError(f"{service_name} setup: Truth key '{TRUTH_KEY}' not found in system-redis")

    try:
        truth = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"{service_name} setup: failed to parse Truth JSON: {e}") from e

    return truth


def setup(service_name: str = SERVICE_NAME) -> Dict[str, Any]:
    """
    Generic setup entrypoint used by main.py.

    Returns a config dict with at least:
      - service_name
      - truth
      - truth_redis_url
      - truth_key
      - component
      - buses
      - inputs
      - outputs
      - heartbeat
    """
    logutil.log(service_name, "INFO", "⚙️", "Setting up environment")

    # ------------------------------------------------------------------
    # 1. Connect to system-redis (Truth + governance bus)
    # ------------------------------------------------------------------
    system_redis_url = os.getenv("SYSTEM_REDIS_URL", "redis://127.0.0.1:6379")
    sys_r = _redis_from_url(system_redis_url)
    try:
        sys_r.ping()
        logutil.log(service_name, "INFO", "✅", f"Connected to system-redis at {system_redis_url}")
    except Exception as e:
        raise RuntimeError(f"{service_name} setup: cannot connect to system-redis ({system_redis_url}): {e}") from e

    # ------------------------------------------------------------------
    # 2. Load Truth and locate this component
    # ------------------------------------------------------------------
    truth = _load_truth(sys_r, service_name)

    components = truth.get("components", {})
    component = components.get(service_name)
    if not component:
        raise RuntimeError(f"{service_name} setup: component '{service_name}' not found in Truth")

    buses = truth.get("buses", {}) or {}
    bus_urls: Dict[str, str] = {}
    for bus_name, bus_cfg in buses.items():
        url = bus_cfg.get("url")
        if url:
            bus_urls[bus_name] = url

    # ------------------------------------------------------------------
    # 3. Build normalized inputs/outputs with redis_url
    # ------------------------------------------------------------------
    access_points = component.get("access_points", {}) or {}
    publish_to = access_points.get("publish_to", []) or []
    subscribe_to = access_points.get("subscribe_to", []) or []

    outputs = []
    for ep in publish_to:
        bus = ep.get("bus")
        key = ep.get("key")
        if not bus or not key:
            continue
        redis_url = bus_urls.get(bus, system_redis_url)
        outputs.append(
            {
                "bus": bus,
                "key": key,
                "redis_url": redis_url,
            }
        )

    inputs = []
    for ep in subscribe_to:
        bus = ep.get("bus")
        key = ep.get("key")
        if not bus or not key:
            continue
        redis_url = bus_urls.get(bus, system_redis_url)
        inputs.append(
            {
                "bus": bus,
                "key": key,
                "redis_url": redis_url,
            }
        )

    # ------------------------------------------------------------------
    # 4. Heartbeat configuration
    # ------------------------------------------------------------------
    hb_cfg = component.get("heartbeat", {}) or {}

    config: Dict[str, Any] = {
        "service_name": service_name,
        "truth": truth,
        "truth_redis_url": system_redis_url,
        "truth_key": TRUTH_KEY,
        "component": component,
        "buses": buses,
        "inputs": inputs,
        "outputs": outputs,
        "heartbeat": hb_cfg,
    }

    logutil.log(service_name, "INFO", "✅", f"setup() built config for service='{service_name}'")
    return config