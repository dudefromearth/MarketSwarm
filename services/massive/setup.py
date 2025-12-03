#!/usr/bin/env python3
"""
setup.py — Massive service configuration loader

Responsibilities:
- Connect to system-redis and load truth.json from key "truth"
- Extract the Massive component block
- Parse workflow, access points, models, domain keys, heartbeat
- Resolve API keys and Redis URLs from environment
- Build runtime wiring for orchestrator (Python, chain loader, scheduler)
- Emit a human-readable config dump on startup
"""

import json
import os
import sys
from datetime import datetime, timezone

import redis


TRUTH_KEY = "truth"


# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
def log(stage: str, emoji: str, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}][massive|{stage}]{emoji} {msg}")


# ----------------------------------------------------------------------
# Redis client builder
# ----------------------------------------------------------------------
def make_redis_client(url: str) -> redis.Redis:
    return redis.Redis.from_url(url, decode_responses=True)


# ----------------------------------------------------------------------
# Load truth.json from system-redis
# ----------------------------------------------------------------------
def load_truth_from_system(r_system: redis.Redis) -> dict:
    raw = r_system.get(TRUTH_KEY)
    if not raw:
        raise RuntimeError("truth.json not found in system-redis (key 'truth')")

    try:
        truth = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"truth.json in system-redis is invalid JSON: {e}")

    return truth


# ----------------------------------------------------------------------
# Extract Massive config block
# ----------------------------------------------------------------------
def extract_massive_block(truth: dict) -> dict:
    """
    Expects truth structure like:
        {
          "components": {
            "massive": { ... }
          },
          ...
        }
    """
    comps = truth.get("components")
    if not comps or "massive" not in comps:
        raise RuntimeError("truth.json missing components.massive block")

    return comps["massive"]


# ----------------------------------------------------------------------
# Validate & parse workflow section
# ----------------------------------------------------------------------
def parse_workflow(block: dict) -> dict:
    wf = block.get("workflow")
    if not wf:
        raise RuntimeError("massive.workflow block missing")

    symbols = wf.get("symbols")
    strike_ranges = wf.get("strike_ranges")
    num_exp = wf.get("num_expirations")
    api_env = wf.get("api_key_env")

    if not symbols:
        raise RuntimeError("massive.workflow.symbols missing")

    if not strike_ranges:
        raise RuntimeError("massive.workflow.strike_ranges missing")

    if num_exp is None:
        raise RuntimeError("massive.workflow.num_expirations missing")

    if not api_env:
        raise RuntimeError("massive.workflow.api_key_env missing")

    use_strict = wf.get("use_strict_gt_lt", False)
    redis_prefix = wf.get("redis_prefix", "chain")
    poll_interval = wf.get("poll_interval_sec", 10)
    threading_enabled = wf.get("threading_enabled", True)

    return {
        "symbols": symbols,
        "strike_ranges": strike_ranges,
        "num_expirations": num_exp,
        "use_strict": use_strict,
        "redis_prefix": redis_prefix,
        "poll_interval": poll_interval,
        "threading_enabled": threading_enabled,
        "api_key_env": api_env,
    }


# ----------------------------------------------------------------------
# Extract access_points → publish_to & subscribe_to
# ----------------------------------------------------------------------
def parse_access_points(block: dict) -> dict:
    ap = block.get("access_points", {}) or {}
    return {
        "publish_to": ap.get("publish_to", []) or [],
        "subscribe_to": ap.get("subscribe_to", []) or [],
    }


# ----------------------------------------------------------------------
# Extract models produced/consumed
# ----------------------------------------------------------------------
def parse_models(block: dict) -> dict:
    models = block.get("models", {}) or {}
    return {
        "produces": models.get("produces", []) or [],
        "consumes": models.get("consumes", []) or [],
    }


# ----------------------------------------------------------------------
# Extract domain_keys
# ----------------------------------------------------------------------
def parse_domain_keys(block: dict) -> list:
    return block.get("domain_keys", []) or []


# ----------------------------------------------------------------------
# Heartbeat config
# ----------------------------------------------------------------------
def parse_heartbeat(block: dict) -> dict:
    hb = block.get("heartbeat", {}) or {}
    if "interval_sec" not in hb or "ttl_sec" not in hb or "channel" not in hb:
        raise RuntimeError("massive.heartbeat missing required fields")

    return {
        "interval_sec": hb["interval_sec"],
        "ttl_sec": hb["ttl_sec"],
        "channel": hb["channel"],
    }


# ----------------------------------------------------------------------
# Main Massive setup
# ----------------------------------------------------------------------
def setup_environment() -> dict:
    # 1. Connect to system-redis to load truth
    system_url = (
        os.getenv("SYSTEM_REDIS_URL")
        or os.getenv("REDIS_SYSTEM_URL")
        or "redis://127.0.0.1:6379"
    )
    r_system = make_redis_client(system_url)

    log("setup", "🔍", f"Loading truth.json from system-redis → {system_url}")

    truth = load_truth_from_system(r_system)
    massive_block = extract_massive_block(truth)

    # 2. Parse block sections
    workflow = parse_workflow(massive_block)
    access_points = parse_access_points(massive_block)
    models = parse_models(massive_block)
    domain_keys = parse_domain_keys(massive_block)
    heartbeat = parse_heartbeat(massive_block)

    # 2a. Optional symbol selection via env MASSIVE_SYMBOL
    # If set, we FILTER the configured symbol list to only that symbol.
    # If the chosen symbol is not present in workflow.symbols, we fail fast.
    symbol_env = os.getenv("MASSIVE_SYMBOL")
    if symbol_env:
        chosen = symbol_env.strip()
        if chosen:
            original_symbols = workflow["symbols"]
            filtered = [s for s in original_symbols if s == chosen]

            if not filtered:
                raise RuntimeError(
                    f"MASSIVE_SYMBOL='{chosen}' not found in workflow.symbols {original_symbols}"
                )

            workflow["symbols"] = filtered
            log(
                "setup",
                "🎯",
                f"Symbol filter: workflow.symbols → {workflow['symbols']} "
                f"(from MASSIVE_SYMBOL='{chosen}')",
            )

    # 3. API key extraction (env var name defined in workflow.api_key_env)
    api_key_env = workflow["api_key_env"]
    api_key = os.getenv(api_key_env, "")

    # 4. Market-redis client for model output
    market_url = (
        os.getenv("MARKET_REDIS_URL")
        or os.getenv("REDIS_MARKET_URL")
        or "redis://127.0.0.1:6380"
    )
    r_market = make_redis_client(market_url)

    # 5. SERVICE_ID used for heartbeat / logs (env wins)
    service_id = os.getenv("SERVICE_ID", "massive")

    # 6. Orchestrator / runtime wiring
    python_bin = os.getenv("PYTHON_BIN", sys.executable)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    chain_loader_path = os.getenv(
        "MASSIVE_CHAIN_LOADER",
        os.path.join(base_dir, "massive_chain_loader.py"),
    )

    # 7. Throttling / scheduler config (0DTE vs multi-DTE — mutually exclusive)
    #
    # Fast lane (0DTE)
    fast_interval = float(os.getenv("MASSIVE_0DTE_INTERVAL_SEC", "1"))
    fast_num_exp = int(os.getenv("MASSIVE_0DTE_NUM_EXP", "1"))

    # Rest lane (multi-DTE, e.g. 1–N) – defaults to workflow values if unset
    rest_interval = float(
        os.getenv("MASSIVE_REST_INTERVAL_SEC", str(workflow["poll_interval"]))
    )
    rest_num_exp = int(
        os.getenv("MASSIVE_REST_NUM_EXP", str(workflow["num_expirations"]))
    )

    # Mode selection:
    #   - If fast_num_exp > 0 → 0DTE-only (rest lane is disabled, even if configured)
    #   - Else if rest_num_exp > 0 → multi-DTE mode
    #   - Else → nothing to fetch (mode = "off")
    mode = "off"

    if fast_num_exp > 0:
        mode = "0dte"
        if rest_num_exp > 0:
            log(
                "setup",
                "⚠️",
                "Both 0DTE and multi-DTE configured; enforcing 0DTE-only for this instance "
                "(MASSIVE_REST_NUM_EXP ignored).",
            )
            rest_num_exp = 0
    elif rest_num_exp > 0:
        mode = "multi"

    scheduler = {
        "mode": mode,
        "fast_interval": fast_interval,
        "fast_num_expirations": fast_num_exp,
        "rest_interval": rest_interval,
        "rest_num_expirations": rest_num_exp,
    }

    # 8. Debug flags
    debug_massive = os.getenv("DEBUG_MASSIVE", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    debug_rest = os.getenv("MASSIVE_DEBUG_REST", "0").lower() in (
        "1",
        "true",
        "yes",
    )
    debug_threads = os.getenv("MASSIVE_DEBUG_THREADS", "0").lower() in (
        "1",
        "true",
        "yes",
    )

    # 9. Log final resolved configuration
    log("setup", "📡", "Massive configuration loaded:")
    print("")
    print(" ┌────────────────────────────────────────────")
    print(" │ ACCESS POINTS")
    print(" ├────────────────────────────────────────────")
    for ap in access_points["publish_to"]:
        print(f" │   publish   → {ap.get('bus', '?')} :: {ap.get('key', '?')}")
    if access_points["subscribe_to"]:
        print(" ├────────────────────────────────────────────")
        for ap in access_points["subscribe_to"]:
            print(f" │   subscribe → {ap.get('bus', '?')} :: {ap.get('key', '?')}")
    else:
        print(" │   subscribe → (none)")

    print(" ├────────────────────────────────────────────")
    print(" │ WORKFLOW")
    print(" ├────────────────────────────────────────────")
    print(f" │   symbols:            {workflow['symbols']}")
    print(f" │   strike_ranges:      {workflow['strike_ranges']}")
    print(f" │   num_expirations:    {workflow['num_expirations']}")
    print(f" │   strict gt/lt:       {workflow['use_strict']}")
    print(f" │   redis_prefix:       {workflow['redis_prefix']}")
    print(f" │   poll_interval_sec:  {workflow['poll_interval']}")
    print(f" │   threading_enabled:  {workflow['threading_enabled']}")
    print(f" │   api_key_env:        {workflow['api_key_env']}")
    print(" ├────────────────────────────────────────────")
    print(" │ MODELS")
    print(" ├────────────────────────────────────────────")
    if models["produces"]:
        for m in models["produces"]:
            print(f" │   produces → {m}")
    else:
        print(" │   produces → (none)")
    print(" ├────────────────────────────────────────────")
    if models["consumes"]:
        for m in models["consumes"]:
            print(f" │   consumes → {m}")
    else:
        print(" │   consumes → (none)")

    print(" ├────────────────────────────────────────────")
    print(" │ DOMAIN KEYS")
    print(" ├────────────────────────────────────────────")
    if domain_keys:
        for dk in domain_keys:
            print(f" │   {dk}")
    else:
        print(" │   (none)")

    print(" ├────────────────────────────────────────────")
    print(" │ HEARTBEAT")
    print(" ├────────────────────────────────────────────")
    print(f" │   interval_sec: {heartbeat['interval_sec']}")
    print(f" │   ttl_sec:      {heartbeat['ttl_sec']}")
    print(f" │   channel:      {heartbeat['channel']}")

    print(" ├────────────────────────────────────────────")
    print(" │ SCHEDULER (DTE Throttling)")
    print(" ├────────────────────────────────────────────")
    print(
        f" │   fast: {scheduler['fast_num_expirations']} exp(s) "
        f"every {scheduler['fast_interval']}s"
    )
    print(
        f" │   rest: {scheduler['rest_num_expirations']} exp(s) "
        f"every {scheduler['rest_interval']}s"
    )

    print(" ├────────────────────────────────────────────")
    print(" │ REDIS & RUNTIME")
    print(" ├────────────────────────────────────────────")
    print(f" │   system_redis_url:   {system_url}")
    print(f" │   market_redis_url:   {market_url}")
    print(f" │   SERVICE_ID:         {service_id}")
    print(f" │   PYTHON_BIN:         {python_bin}")
    print(f" │   CHAIN_LOADER:       {chain_loader_path}")
    print(f" │   DEBUG_MASSIVE:      {debug_massive}")
    print(f" │   DEBUG_REST:         {debug_rest}")
    print(f" │   DEBUG_THREADS:      {debug_threads}")
    print(" └────────────────────────────────────────────")
    print("")

    # 10. Return consolidated configuration
    return {
        "SERVICE_ID": service_id,
        "truth": truth,
        "workflow": workflow,
        "access_points": access_points,
        "models": models,
        "domain_keys": domain_keys,
        "heartbeat": heartbeat,
        "api_key": api_key,
        "r_system": r_system,
        "r_market": r_market,
        # Orchestrator wiring
        "redis_market_url": market_url,
        "PYTHON": python_bin,
        "CHAIN_LOADER": chain_loader_path,
        "debug_massive": debug_massive,
        "debug_rest": debug_rest,
        "debug_threads": debug_threads,
        # DTE throttling scheduler
        "scheduler": scheduler,
    }