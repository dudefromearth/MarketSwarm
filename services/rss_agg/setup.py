#!/usr/bin/env python3
"""
setup.py — RSS Aggregator environment setup.
Loads truth, discovers access points, loads local JSON config,
initializes Redis structures, and verifies readiness.
"""

import os
import json
import redis
from typing import Dict, Any


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def load_truth(r: redis.Redis) -> Dict[str, Any]:
    """Load the canonical truth document from system-redis."""
    raw = r.get("truth")
    if not raw:
        raise RuntimeError("❌ truth key not found in system-redis")

    try:
        truth = json.loads(raw)
        print("📘 Loaded truth from Redis (truth key).")
        return truth
    except Exception as e:
        raise RuntimeError(f"❌ Failed to parse truth JSON: {e}")


def load_json(path: str) -> Dict[str, Any]:
    """Load a local JSON config file with sanity checks."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"❌ Required config file missing: {path}")

    with open(path, "r") as f:
        return json.load(f)


# -------------------------------------------------------
# Redis Key Creation Helpers
# -------------------------------------------------------

def ensure_key(r: redis.Redis, key: str, type_: str):
    """Ensure a key exists with the proper type (best-effort)."""

    exists = r.exists(key)

    if exists:
        return

    # Create minimal structures so Redis assigns the type
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

    print(f"   → Created {key} ({type_})")


def verify_key_type(r: redis.Redis, key: str, type_: str):
    """Verify the Redis key type matches expectation."""
    t = r.type(key)   # <-- FIXED: no .decode()

    # Translate Redis types
    mapping = {
        "hash": "HASH",
        "set": "SET",
        "zset": "ZSET",
        "stream": "STREAM",
        "none": "NONE"
    }

    redis_type = mapping.get(t, "OTHER")

    if redis_type != type_:
        raise RuntimeError(f"❌ Key {key} has wrong type: {redis_type} (expected {type_})")

    print(f"   • Verified {key} [{redis_type}]")


# -------------------------------------------------------
# Main Setup
# -------------------------------------------------------

def setup_service_environment(svc: str) -> Dict[str, Any]:
    print(f"⚙️ Setting up environment for service: {svc}")

    # ---------------------------------------------
    # 1. Connect to SYSTEM REDIS to load truth
    # ---------------------------------------------
    sys_host = os.getenv("SYSTEM_REDIS_HOST", "127.0.0.1")
    sys_port = int(os.getenv("SYSTEM_REDIS_PORT", "6379"))
    system_r = redis.Redis(host=sys_host, port=sys_port, decode_responses=True)

    try:
        system_r.ping()
        print(f"✅ Connected to system-redis at {sys_host}:{sys_port}")
    except Exception as e:
        raise RuntimeError(f"❌ Cannot connect to system-redis: {e}")

    # ---------------------------------------------
    # 2. Load truth and identify component
    # ---------------------------------------------
    truth = load_truth(system_r)

    components = truth.get("components", {})
    comp = components.get("rss_agg")
    if not comp:
        raise RuntimeError("❌ rss_agg component not found in truth.json")

    print("📘 Located rss_agg component in truth.")

    access = comp.get("access_points", {})
    if not access:
        raise RuntimeError("❌ No access_points defined in truth for rss_agg")

    print("📡 Access points discovered.")

    # ---------------------------------------------
    # 3. Connect to Intel Redis
    # ---------------------------------------------
    intel_host = os.getenv("INTEL_REDIS_HOST", "127.0.0.1")
    intel_port = int(os.getenv("INTEL_REDIS_PORT", "6381"))
    intel_r = redis.Redis(host=intel_host, port=intel_port, decode_responses=True)

    try:
        intel_r.ping()
        print(f"✅ Connected to intel-redis at {intel_host}:{intel_port}")
    except Exception as e:
        raise RuntimeError(f"❌ Cannot connect to intel-redis: {e}")

    # ---------------------------------------------
    # 4. Load local JSON configs
    # ---------------------------------------------
    root = os.getcwd()
    feeds_path = os.path.join(root, "services/rss_agg/schema/feeds.json")
    articles_path = os.path.join(root, "services/rss_agg/schema/articles.json")

    feeds_cfg = load_json(feeds_path)
    articles_cfg = load_json(articles_path)

    print("📄 Loaded feeds.json and articles.json")

    # ---------------------------------------------
    # 5. Initialize Redis structures
    # ---------------------------------------------
    print("🧩 Initializing required Redis structures...")

    for k in articles_cfg["keys"]:
        tmpl = k["name"]
        # Replace template with placeholder, but users will create real ones during ingestion
        key = tmpl.replace("{uid}", "_init")
        type_ = k["type"]

        ensure_key(intel_r, key, type_)
        verify_key_type(intel_r, key, type_)

    # ---------------------------------------------
    # 6. Apply TTLs
    # ---------------------------------------------
    print("⏱️ Applying TTLs...")

    for pattern, ttl in articles_cfg["global_ttls"].items():
        key = pattern.replace("{uid}", "_init")
        intel_r.expire(key, ttl)
        print(f"   • TTL set for {key}: {ttl}s")

    print("✅ Setup complete.\n")

    # ---------------------------------------------
    # 7. Return configuration for main.py
    # ---------------------------------------------
    return {
        "truth": truth,
        "feeds_cfg": feeds_cfg,
        "articles_cfg": articles_cfg,
        "access_points": access,
        "intel_redis": {"host": intel_host, "port": intel_port},
        "system_redis": {"host": sys_host, "port": sys_port}
    }