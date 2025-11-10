#!/usr/bin/env python3
"""
setup.py — Initialization & verification for RSS Aggregator service.
Ensures required Redis structures and filesystem directories exist.
"""

import os
import json
import redis


def setup_service_environment(svc: str):
    print(f"⚙️ Setting up working environment for {svc}...")

    try:
        # Connect to System Redis
        r = redis.Redis(host=os.getenv("SYSTEM_REDIS_HOST", "localhost"), port=6379, decode_responses=True)
        r.ping()
        print("✅ Connected to system-redis:6379")
    except Exception as e:
        raise RuntimeError(f"❌ Failed to connect to Redis: {e}")

    # Schema paths
    feeds_schema_path = "/Users/ernie/MarketSwarm/scripts/rssagg/feeds.json"
    articles_schema_path = "/Users/ernie/MarketSwarm/scripts/rssagg/articles.json"

    # Check that schema files exist
    for path in (feeds_schema_path, articles_schema_path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"❌ Missing schema file: {path}")
        else:
            print(f"📖 Found schema: {os.path.basename(path)}")

    # Load schema definitions
    with open(feeds_schema_path, "r") as f:
        feeds_cfg = json.load(f)
    with open(articles_schema_path, "r") as f:
        articles_cfg = json.load(f)

    # Initialize Redis structures
    print("🧩 Initializing Redis domain structures...")
    created, existing = 0, 0

    for keydef in articles_cfg.get("keys", []):
        key_name = keydef["name"].replace("{uid}", "placeholder")
        key_root = key_name.split(":")[0]
        exists = r.exists(key_root)

        if not exists:
            created += 1
            print(f" - Creating {key_name} ({keydef['type']})")
            try:
                if keydef["type"] == "SET":
                    r.sadd(key_name, "")
                elif keydef["type"] == "ZSET":
                    r.zadd(key_name, {"placeholder": 0})
                elif keydef["type"] == "STREAM":
                    r.xadd(key_name, {"uid": "init", "abstract": "ready"})
                elif keydef["type"] == "HASH":
                    r.hset(key_name, mapping={"title": "init"})
            except Exception as e:
                print(f"   ⚠️ Failed to create {key_name}: {e}")
        else:
            existing += 1
            print(f" - {key_name} already exists (skipped)")

    # TTL setup and verification
    print("⏱️  Applying TTLs...")
    for key_pattern, ttl in articles_cfg.get("global_ttls", {}).items():
        key_root = key_pattern.split(":")[0]
        try:
            r.expire(key_root, ttl)
            actual_ttl = r.ttl(key_root)
            print(f"   • TTL set for {key_root}: {actual_ttl}s (target {ttl}s)")
        except Exception as e:
            print(f"   ⚠️ TTL setup failed for {key_root}: {e}")

    # Filesystem check (Docker-safe + local-safe)
    feeds_dir = os.getenv("FEEDS_DIR", "./feeds")
    if not os.path.isabs(feeds_dir):
        feeds_dir = os.path.join(os.getcwd(), feeds_dir)

    try:
        os.makedirs(feeds_dir, exist_ok=True)
        print(f"📦 Verified {feeds_dir} directory for published RSS files")
    except Exception as e:
        raise RuntimeError(f"❌ Failed to create feeds directory at {feeds_dir}: {e}")