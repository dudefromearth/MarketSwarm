# services/mmaker/setup.py

import json
import os
from typing import Any, Dict, List

from redis import Redis  # sync client for truth load
from redis.asyncio import Redis as AsyncRedis  # async for shared use


def _load_truth_from_redis(service_name: str) -> Dict[str, Any]:
    """
    Load the composite Truth document from Redis.

    Env:
      TRUTH_REDIS_URL  (optional) – full redis:// URL for Truth
      SYSTEM_REDIS_URL (fallback) – system redis URL, default redis://127.0.0.1:6379
      TRUTH_REDIS_KEY  (optional) – key name, default "truth"
    """
    truth_url = (
        os.getenv("TRUTH_REDIS_URL")
        or os.getenv("SYSTEM_REDIS_URL", "redis://127.0.0.1:6379")
    )
    truth_key = os.getenv("TRUTH_REDIS_KEY", "truth")

    print(f"[setup:{service_name}] Loading Truth from Redis (url={truth_url}, key={truth_key})")

    r = Redis.from_url(truth_url, decode_responses=True)

    raw = r.get(truth_key)
    if not raw:
        raise RuntimeError(
            f"[setup:{service_name}] Truth key '{truth_key}' is empty or missing in Redis at {truth_url}"
        )

    try:
        truth = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"[setup:{service_name}] Failed to decode Truth JSON: {e}") from e

    return {
        "truth": truth,
        "truth_url": truth_url,
        "truth_key": truth_key,
    }


def setup(service_name: str = "mmaker") -> Dict[str, Any]:
    """
    Initialize the mmaker service from Truth stored in Redis.

    - Loads Truth from Redis
    - Extracts the 'mmaker' component definition
    - Resolves Redis URLs for subscribe/publish endpoints
    - Creates shared async Redis object for primary bus
    - Returns a config dict for the orchestrator + heartbeat
    """
    env = _load_truth_from_redis(service_name)
    truth: Dict[str, Any] = env["truth"]
    truth_url: str = env["truth_url"]
    truth_key: str = env["truth_key"]

    buses: Dict[str, Any] = truth.get("buses", {})
    components: Dict[str, Any] = truth.get("components", {})
    comp: Dict[str, Any] = components.get(service_name, {})

    if not comp:
        raise RuntimeError(
            f"[setup:{service_name}] Component '{service_name}' not found in Truth (key={truth_key})"
        )

    meta = comp.get("meta", {})
    access_points = comp.get("access_points", {})
    heartbeat_cfg = comp.get("heartbeat", {})
    models_cfg = comp.get("models", {})
    domain_keys: List[str] = comp.get("domain_keys", [])
    dependencies: List[str] = comp.get("dependencies", [])

    # Resolve subscribe endpoints with Redis URLs
    subscribe_to = access_points.get("subscribe_to", [])
    inputs: List[Dict[str, Any]] = []
    for sub in subscribe_to:
        bus_name = sub.get("bus")
        key = sub.get("key")
        if not bus_name or not key:
            continue
        bus_cfg = buses.get(bus_name, {})
        redis_url = bus_cfg.get(
            "url",
            os.getenv("REDIS_URL", "redis://localhost:6379"),
        )
        inputs.append(
            {
                "bus": bus_name,
                "key": key,
                "redis_url": redis_url,
            }
        )

    # Resolve publish endpoints with Redis URLs
    publish_to = access_points.get("publish_to", [])
    outputs: List[Dict[str, Any]] = []
    for pub in publish_to:
        bus_name = pub.get("bus")
        key = pub.get("key")
        if not bus_name or not key:
            continue
        bus_cfg = buses.get(bus_name, {})
        redis_url = bus_cfg.get(
            "url",
            os.getenv("REDIS_URL", "redis://localhost:6379"),
        )
        outputs.append(
            {
                "bus": bus_name,
                "key": key,
                "redis_url": redis_url,
            }
        )

    # Build a simple config dict for the orchestrator + heartbeat
    config: Dict[str, Any] = {
        "service_name": service_name,
        "meta": {
            "name": meta.get("name", service_name),
            "description": meta.get("description", ""),
        },
        # Truth location is now Redis, not a file path
        "truth_url": truth_url,
        "truth_key": truth_key,
        "heartbeat": {
            "interval_sec": heartbeat_cfg.get("interval_sec", 10),
            "ttl_sec": heartbeat_cfg.get("ttl_sec", 30),
        },
        "inputs": inputs,
        "outputs": outputs,
        "models": {
            "produces": models_cfg.get("produces", []),
            "consumes": models_cfg.get("consumes", []),
        },
        "domain_keys": domain_keys,
        "dependencies": dependencies,
        # All buses for flexibility (services pick what they need)
        "all_buses": {
            bus_name: bus_cfg.get("url", os.getenv("REDIS_URL", "redis://localhost:6379"))
            for bus_name, bus_cfg in buses.items()
        },
    }

    # Create shared async Redis for primary bus (first input or market fallback)
    primary_bus_url = inputs[0]["redis_url"] if inputs else config["all_buses"].get("market-redis", os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380"))
    shared_primary_redis = AsyncRedis.from_url(primary_bus_url)
    print(f"[setup:{service_name}] Created shared primary Redis: {primary_bus_url}")

    # Add shared resources to config (generic for all services)
    config["shared_resources"] = {
        "primary_redis": shared_primary_redis,
        "primary_redis_url": primary_bus_url,
    }

    print(f"[setup:{service_name}] setup() built config for service='{service_name}'")
    return config