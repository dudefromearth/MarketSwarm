#!/usr/bin/env python3
"""
setup.py — Massive Service Environment Setup

Loads truth, wires Redis clients (system + market), and exposes a config dict
with sensible fallbacks so the service can run even if truth is incomplete.
"""
import json
import os
from urllib.parse import urlparse

import redis


def _redis_from_url(url: str) -> redis.Redis:
    parsed = urlparse(url or "redis://127.0.0.1:6379")
    return redis.Redis(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 6379,
        decode_responses=True,
    )


def _load_truth(r_system: redis.Redis) -> dict:
    """
    Try both truth:doc (preferred) and truth (legacy) to maximize compatibility.
    """
    for key in (os.getenv("TRUTH_KEY") or "truth:doc", "truth"):
        raw = r_system.get(key)
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass
    return {}


def _extract_component(truth: dict, svc: str) -> dict:
    return (truth.get("components", {}) or {}).get(svc, {}) or {}


def _heartbeat_from_component(comp: dict) -> dict:
    hb = comp.get("heartbeat", {}) or {}
    interval_sec = hb.get("interval_sec")
    if interval_sec is None:
        hz = hb.get("interval_hz")
        if hz:
            try:
                interval_sec = max(1.0 / float(hz), 0.1)
            except Exception:
                interval_sec = 5.0
        else:
            interval_sec = 5.0

    return {
        "interval_sec": interval_sec,
        "ttl_sec": hb.get("ttl_sec", 30),
        "channel": hb.get("channel", "massive:heartbeat"),
    }


def _schedules_from_truth(comp: dict) -> dict:
    schedules = comp.get("schedules", {}) or {}
    env = os.getenv
    return {
        "chainfeed": schedules.get("chainfeed", int(env("CHAINFEED_INTERVAL_SEC", "10"))),
        "convexity": schedules.get("convexity", int(env("CONVEXITY_INTERVAL_SEC", "60"))),
        "volume_profile": schedules.get("volume_profile", int(env("VOLUME_PROFILE_INTERVAL_SEC", "60"))),
        "enable_chainfeed": schedules.get("enable_chainfeed", env("ENABLE_CHAINFEED", "true").lower() == "true"),
        "enable_convexity": schedules.get("enable_convexity", env("ENABLE_CONVEXITY", "false").lower() == "true"),
        "enable_volume_profile": schedules.get("enable_volume_profile", env("ENABLE_VOLUME_PROFILE", "false").lower() == "true"),
    }


def setup_environment():
    svc = "massive"

    # Redis clients
    system_url = os.getenv("SYSTEM_REDIS_URL", "redis://127.0.0.1:6379")
    r_system = _redis_from_url(system_url)

    truth = _load_truth(r_system)
    comp = _extract_component(truth, svc)

    buses = truth.get("buses", {}) or {}
    market_url = os.getenv(
        "MARKET_REDIS_URL",
        (buses.get("market-redis") or {}).get("url", "redis://127.0.0.1:6380"),
    )
    r_market = _redis_from_url(market_url)

    heartbeat = _heartbeat_from_component(comp)
    schedules = _schedules_from_truth(comp)

    secrets = truth.get("secrets", {}) or {}
    api_key = os.getenv("MASSIVE_API_KEY") or (secrets.get("massive") or {}).get("api_key")

    # --- Volume Profile startup guard --------------------------------
    # If volume_profile is enabled, require that the base VP model exists
    # in system-redis before starting Massive. This is a manual, pre-start
    # step (vp-backfill.sh / build_volume_profile.py).
    try:
        vp_enabled = schedules.get("enable_volume_profile", False)
        if vp_enabled:
            # Allow future override via truth if desired
            wf = (comp.get("workflow") or {})
            vp_cfg = (wf.get("volume_profile") or {})
            vp_system_key = vp_cfg.get("system_key", "massive:volume_profile")

            vp_raw = r_system.get(vp_system_key)
            if not vp_raw:
                raise RuntimeError(
                    f"Volume Profile model missing in system-redis key '{vp_system_key}'. "
                    f"Massive is configured with volume_profile enabled, so startup is blocked.\n"
                    f"→ Run the VP backfill step (e.g. vp-backfill.sh / build_volume_profile.py) "
                    f"to create the 5-year SPY→SPX Volume Profile model, then restart Massive."
                )
    except redis.RedisError as e:
        # If we can't even reach Redis, fail fast with a clear message.
        raise RuntimeError(
            f"Unable to verify Volume Profile model in system-redis: {e}. "
            f"Check SYSTEM_REDIS_URL and Redis availability."
        )

    return {
        "SERVICE_ID": svc,
        "truth": truth,
        "component": comp,
        "heartbeat": heartbeat,
        "schedules": schedules,
        "api_key": api_key,
        "r_system": r_system,
        "r_market": r_market,
        "massive_base_url": os.getenv(
            "MASSIVE_BASE_URL", "https://api.massive.com/v3/snapshot/options"
        ),
        "chain_stream_maxlen": int(os.getenv("CHAIN_STREAM_MAXLEN", "500")),
    }