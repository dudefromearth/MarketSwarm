#!/usr/bin/env python3
"""
setup.py — Vigil Service Setup
Prepares environment, validates Redis, and returns config for the main runner.
"""

import os
import redis
from datetime import datetime, timezone

SERVICE_ID = "vigil"

def banner(msg: str, emoji="🛡️"):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}][{SERVICE_ID}|setup]{emoji} {msg}")

def setup_environment():
    banner("Starting Vigil setup…", "🚀")

    # Environment defaults
    market_url = os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380")
    system_url = os.getenv("SYSTEM_REDIS_URL", "redis://127.0.0.1:6379")
    debug = os.getenv("VIGIL_DEBUG", "false").lower() == "true"

    banner(f"MARKET_REDIS_URL={market_url}", "⚙️")
    banner(f"SYSTEM_REDIS_URL={system_url}", "⚙️")
    if debug:
        banner("Debug mode enabled", "🐛")

    # Connect to Redis
    try:
        r_market = redis.Redis.from_url(market_url, decode_responses=True)
        r_market.ping()
        banner("Market Redis OK", "📡")
    except Exception:
        banner("Market Redis connection FAILED", "❌")
        raise

    try:
        r_system = redis.Redis.from_url(system_url, decode_responses=True)
        r_system.ping()
        banner("System Redis OK", "📡")
    except Exception:
        banner("System Redis connection FAILED", "❌")
        raise

    banner("Setup complete.", "✅")

    return {
        "SERVICE_ID": SERVICE_ID,
        "debug": debug,
        "r_market": r_market,
        "r_system": r_system,
    }