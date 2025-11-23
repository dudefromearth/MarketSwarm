#!/usr/bin/env python3
"""
setup.py — Content Analysis Engine
Discovers its truth block, builds Redis connections, and returns environment.
"""

import json
import os
import redis

def setup_environment():
    SERVICE_ID = "content_anal"

    # -------------------------------
    # Load truth from system-redis
    # -------------------------------
    r_system = redis.Redis(
        host="127.0.0.1", port=6379, decode_responses=True
    )

    raw_truth = r_system.get("truth")
    if not raw_truth:
        raise RuntimeError("truth.json not loaded into system-redis!")

    truth = json.loads(raw_truth)

    # -------------------------------
    # Discover our own truth block
    # -------------------------------
    try:
        comp = truth["components"][SERVICE_ID]
    except KeyError:
        raise RuntimeError(f"Service '{SERVICE_ID}' missing from truth.json")

    # -------------------------------
    # Redis endpoints
    # -------------------------------
    buses = truth["buses"]

    intel_url = buses["intel-redis"]["url"]
    intel_host, intel_port = intel_url.replace("redis://", "").split(":")

    market_url = buses["market-redis"]["url"]
    market_host, market_port = market_url.replace("redis://", "").split(":")

    r_intel = redis.Redis(host=intel_host, port=intel_port, decode_responses=True)
    r_market = redis.Redis(host=market_host, port=market_port, decode_responses=True)

    return {
        "SERVICE_ID": SERVICE_ID,
        "truth": truth,
        "component": comp,
        "r_system": r_system,
        "r_intel": r_intel,
        "r_market": r_market,
    }