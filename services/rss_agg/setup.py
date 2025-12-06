#!/usr/bin/env python3
"""
setup.py — RSS Aggregator environment setup.

Responsibilities:
  - Connect to system-redis and intel-redis
  - Load Truth from Redis ("truth" key on SYSTEM_REDIS_URL)
  - Discover rss_agg component block
  - Load local JSON configs (feeds.json, articles.json)
  - Initialize required Redis structures on intel-redis
  - Return a config dict consumed by main.py + orchestrator

This follows the MarketSwarm service pattern (mmaker, vigil, etc.).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict
from urllib.parse import urlparse

import redis

import logutil  # services/rss_agg/logutil.py

SERVICE_NAME = os.getenv("SERVICE_ID", "rss_agg")


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def _parse_redis_url(env_var: str, default_url: str) -> str:
    """Return a Redis URL from env, falling back to a default."""
    return os.getenv(env_var, default_url)


def _host_port_from_url(url: str, default_host: str, default_port: int) -> tuple[str, int]:
    """Extract host/port from a redis:// URL with sensible defaults."""
    parsed = urlparse(url)
    host = parsed.hostname or default_host
    port = parsed.port or default_port
    return host, port


def _connect_redis(host: str, port: int, *, decode_responses: bool = True) -> redis.Redis:
    """Create a Redis connection from host/port and ping for liveness."""
    r = redis.Redis(host=host, port=port, decode_responses=decode_responses)
    r.ping()  # fail fast if not reachable
    return r


def _load_truth(system_r: redis.Redis, key: str = "truth") -> Dict[str, Any]:
    """Load the canonical Truth document from system-redis."""
    raw = system_r.get(key)
    if not raw:
        raise RuntimeError(f"truth key '{key}' not found in system-redis")

    try:
        truth = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"failed to parse truth JSON from key '{key}': {e}") from e

    return truth


def _load_json(path: str) -> Dict[str, Any]:
    """Load a local JSON config file with sanity checks."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"required config file missing: {path}")

    with open(path, "r") as f:
        return json.load(f)


# -------------------------------------------------------
# Redis Key Creation Helpers (intel-redis)
# -------------------------------------------------------

def _ensure_key(r: redis.Redis, key: str, type_: str) -> None:
    """Ensure a key exists with the proper type (best-effort)."""
    if r.exists(key):
        return

    if type_ == "HASH":
        r.hset(key, mapping={"init": "1"})
    elif type_ == "SET":
        r.sadd(key, "_init")
    elif type_ == "ZSET":
        r.zadd(key, {"_init": 0})
    elif type_ == "STREAM":
        r.xadd(key, {"init": "1"})
    else:
        raise ValueError(f"Unknown Redis type: {type_}")

    logutil.log(SERVICE_NAME, "INFO", "🧱", f"Created {key} ({type_})")


def _verify_key_type(r: redis.Redis, key: str, type_: str) -> None:
    """Verify the Redis key type matches expectation."""
    t = r.type(key)  # already a string when decode_responses=True

    mapping = {
        "hash": "HASH",
        "set": "SET",
        "zset": "ZSET",
        "stream": "STREAM",
        "none": "NONE",
    }

    redis_type = mapping.get(t, "OTHER")
    if redis_type != type_:
        raise RuntimeError(
            f"Key {key} has wrong type: {redis_type} (expected {type_})"
        )

    logutil.log(SERVICE_NAME, "INFO", "✅", f"Verified {key} [{redis_type}]")


# -------------------------------------------------------
# Main Setup
# -------------------------------------------------------

def setup(service_name: str = SERVICE_NAME) -> Dict[str, Any]:
    """
    Canonical setup() for rss_agg.

    Returns a config dict with at least:
      - service_name
      - meta
      - truth_source  (where Truth came from)
      - truth         (the full Truth document)
      - heartbeat
      - access_points
      - feeds_cfg
      - articles_cfg
      - intel_redis / system_redis connection info (host/port)
    """
    logutil.log(service_name, "INFO", "⚙️", "Setting up environment")

    # ---------------------------------------------
    # 1. Connect to SYSTEM REDIS and load Truth
    # ---------------------------------------------
    system_redis_url = _parse_redis_url(
        "SYSTEM_REDIS_URL", "redis://127.0.0.1:6379"
    )
    sys_host, sys_port = _host_port_from_url(system_redis_url, "127.0.0.1", 6379)

    logutil.log(
        service_name,
        "INFO",
        "📖",
        f"Loading Truth from Redis (url={system_redis_url}, key=truth)",
    )

    sys_r = _connect_redis(sys_host, sys_port, decode_responses=True)
    logutil.log(
        service_name,
        "INFO",
        "✅",
        f"Connected to system-redis at {system_redis_url}",
    )

    truth = _load_truth(sys_r, key="truth")

    # Locate rss_agg component
    components = truth.get("components", {})
    comp = components.get(service_name)
    if not comp:
        raise RuntimeError(f"component '{service_name}' not found in Truth")

    access = comp.get("access_points", {})
    if not access:
        raise RuntimeError(
            f"No access_points defined in Truth for '{service_name}'"
        )

    # ---------------------------------------------
    # 2. Connect to Intel Redis
    # ---------------------------------------------
    intel_redis_url = _parse_redis_url(
        "INTEL_REDIS_URL", "redis://127.0.0.1:6381"
    )
    intel_host, intel_port = _host_port_from_url(intel_redis_url, "127.0.0.1", 6381)

    intel_r = _connect_redis(intel_host, intel_port, decode_responses=True)
    logutil.log(
        service_name,
        "INFO",
        "✅",
        f"Connected to intel-redis at {intel_redis_url}",
    )

    # ---------------------------------------------
    # 3. Load local JSON configs
    # ---------------------------------------------
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    feeds_path = os.path.join(root, "services", "rss_agg", "schema", "feeds.json")
    articles_path = os.path.join(root, "services", "rss_agg", "schema", "articles.json")

    feeds_cfg = _load_json(feeds_path)
    articles_cfg = _load_json(articles_path)

    logutil.log(service_name, "INFO", "📄", f"Loaded {feeds_path}")
    logutil.log(service_name, "INFO", "📄", f"Loaded {articles_path}")

    # ---------------------------------------------
    # 4. Initialize Redis structures on intel-redis
    # ---------------------------------------------
    logutil.log(
        service_name,
        "INFO",
        "🧩",
        "Initializing required Redis structures on intel-redis...",
    )

    for k in articles_cfg.get("keys", []):
        tmpl = k["name"]
        key = tmpl.replace("{uid}", "_init")  # placeholder
        type_ = k["type"]

        _ensure_key(intel_r, key, type_)
        _verify_key_type(intel_r, key, type_)

    # ---------------------------------------------
    # 5. Apply TTLs
    # ---------------------------------------------
    logutil.log(service_name, "INFO", "⏱️", "Applying TTLs...")

    for pattern, ttl in articles_cfg.get("global_ttls", {}).items():
        key = pattern.replace("{uid}", "_init")
        intel_r.expire(key, ttl)
        logutil.log(
            service_name,
            "INFO",
            "⏱️",
            f"TTL set for {key}: {ttl}s",
        )

    # ---------------------------------------------
    # 6. Build config dict (including Truth)
    # ---------------------------------------------
    heartbeat_cfg = comp.get("heartbeat", {})

    config: Dict[str, Any] = {
        "service_name": service_name,
        "meta": comp.get("meta", {}),

        # Where Truth came from
        "truth_source": {
            "redis_url": system_redis_url,
            "key": "truth",
        },

        # 🔑 Orchestrator expects this:
        "truth": truth,

        # Heartbeat + wiring
        "heartbeat": {
            "interval_sec": heartbeat_cfg.get("interval_sec", 10),
            "ttl_sec": heartbeat_cfg.get("ttl_sec", 30),
        },
        "access_points": access,

        # rss_agg-specific configs
        "feeds_cfg": feeds_cfg,
        "articles_cfg": articles_cfg,

        # Redis connection info (host/port) – matches orchestrator expectations
        "intel_redis": {"host": intel_host, "port": intel_port},
        "system_redis": {"host": sys_host, "port": sys_port},
    }

    logutil.log(
        service_name,
        "INFO",
        "✅",
        f"setup() built config for service='{service_name}'",
    )

    return config