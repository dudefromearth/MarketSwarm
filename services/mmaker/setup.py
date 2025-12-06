# services/mmaker/setup.py

import json
import os
from typing import Any, Dict, List

from redis import Redis


def _log(message: str) -> None:
    """Lightweight local logger just for setup."""
    print(f"[setup:mmaker] {message}")


def _load_truth_from_redis() -> Dict[str, Any]:
    """
    Load the composite Truth document from Redis.

    Env:
      SYSTEM_REDIS_URL  – canonical system bus URL (preferred)
      REDIS_URL         – fallback if SYSTEM_REDIS_URL not set
      TRUTH_REDIS_KEY   – key where composite Truth is stored (default: 'truth')
    """
    redis_url = os.getenv("SYSTEM_REDIS_URL", os.getenv("REDIS_URL", "redis://127.0.0.1:6379"))
    truth_key = os.getenv("TRUTH_REDIS_KEY", "truth")

    _log(f"Loading Truth from Redis (url={redis_url}, key={truth_key})")

    r = Redis.from_url(redis_url, decode_responses=True)
    raw = r.get(truth_key)

    if not raw:
        raise RuntimeError(
            f"Truth key '{truth_key}' not found or empty in Redis at {redis_url}. "
            f"Did you run ms-truth.sh / build_truth.py to publish Truth?"
        )

    try:
        truth = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON in Truth key '{truth_key}' from {redis_url}: {e}") from e

    return truth


def setup(service_name: str | None = None) -> Dict[str, Any]:
    """
    Initialize the mmaker service from Truth stored in Redis.

    - Resolves `service_name` (default from SERVICE_ID env)
    - Loads composite Truth from system-redis
    - Extracts this component's definition
    - Resolves subscribe/publish endpoints into concrete Redis URLs
    - Returns a config dict for main/orchestrator/heartbeat
    """
    if service_name is None:
        service_name = os.getenv("SERVICE_ID", "mmaker")

    truth = _load_truth_from_redis()

    buses: Dict[str, Any] = truth.get("buses", {})
    components: Dict[str, Any] = truth.get("components", {})
    comp: Dict[str, Any] = components.get(service_name, {})

    if not comp:
        raise RuntimeError(
            f"Component '{service_name}' not found in Truth "
            f"(components.keys={list(components.keys())})"
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
        bus_cfg = buses.get(bus_name, {})
        redis_url = bus_cfg.get("url", os.getenv("REDIS_URL", "redis://127.0.0.1:6379"))
        if bus_name and key:
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
        bus_cfg = buses.get(bus_name, {})
        redis_url = bus_cfg.get("url", os.getenv("REDIS_URL", "redis://127.0.0.1:6379"))
        if bus_name and key:
            outputs.append(
                {
                    "bus": bus_name,
                    "key": key,
                    "redis_url": redis_url,
                }
            )

    # For logging in main.py, we keep a "truth_path" string that now
    # describes the Redis source instead of a filesystem path.
    redis_url = os.getenv("SYSTEM_REDIS_URL", os.getenv("REDIS_URL", "redis://127.0.0.1:6379"))
    truth_key = os.getenv("TRUTH_REDIS_KEY", "truth")
    truth_source = f"{redis_url} key={truth_key}"

    config: Dict[str, Any] = {
        "service_name": service_name,
        "meta": {
            "name": meta.get("name", service_name),
            "description": meta.get("description", ""),
        },
        "truth_path": truth_source,
        "heartbeat": {
            "interval_sec": heartbeat_cfg.get("interval_sec", 10),
            "ttl_sec": heartbeat_cfg.get("ttl_sec", 30),
        },
        "inputs": inputs,    # where mmaker reads from (e.g., massive:chain on market-redis)
        "outputs": outputs,  # where mmaker writes heartbeats (and eventually models)
        "models": {
            "produces": models_cfg.get("produces", []),
            "consumes": models_cfg.get("consumes", []),
        },
        "domain_keys": domain_keys,
        "dependencies": dependencies,
    }

    _log(f"setup() built config for service='{service_name}'")
    return config