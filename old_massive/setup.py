#!/usr/bin/env python3
"""
setup.py — Massive service setup

Loads Truth from system-redis, resolves the Massive component,
and builds a config dict consumed by main.py + orchestrator.

Key responsibilities:
  - Connect to SYSTEM_REDIS_URL
  - Load Truth from the configured key (default: "truth")
  - Extract component["workflow"] and heartbeat
  - Wire scheduler defaults from workflow
  - Resolve paths for:
      * PYTHON (venv or env override)
      * CHAIN_LOADER (massive_chain_loader.py)
  - Surface API key via workflow["api_key_env"]
  - Allow dev overrides via env (e.g. MASSIVE_SYMBOL)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

import redis

import logutil  # services/massive/logutil.py


# -------------------------------------------------------
# Redis helpers
# -------------------------------------------------------

def _redis_from_url(url: str) -> redis.Redis:
    parsed = urlparse(url or "redis://127.0.0.1:6379")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6379
    return redis.Redis(host=host, port=port, decode_responses=True)


def _load_truth(system_url: str, truth_key: str, service_name: str) -> Dict[str, Any]:
    """
    Load the canonical Truth document from system-redis.
    """
    r = _redis_from_url(system_url)
    logutil.log(
        service_name,
        "INFO",
        "📖",
        f"Loading Truth from Redis (url={system_url}, key={truth_key})",
    )

    raw = r.get(truth_key)
    if not raw:
        raise RuntimeError(f"truth key '{truth_key}' not found in system-redis")

    try:
        return json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"failed to parse Truth JSON from key '{truth_key}': {e}")


# -------------------------------------------------------
# Main setup
# -------------------------------------------------------

def setup(service_name: str = "massive") -> Dict[str, Any]:
    """
    Build Massive config dict from Truth + env.

    Returns a dict consumed by main.py and orchestrator.py with keys:
      - service_name
      - truth_url, truth_key, truth_path, truth
      - component
      - heartbeat
      - workflow
      - scheduler
      - redis_market_url
      - CHAIN_LOADER
      - PYTHON
      - api_key
      - debug_rest, debug_threads
    """
    logutil.log(service_name, "INFO", "⚙️", "Setting up environment")

    # ---------------------------------------------------
    # 1) Truth from system-redis
    # ---------------------------------------------------
    system_url = os.getenv("SYSTEM_REDIS_URL", "redis://127.0.0.1:6379")
    truth_key = os.getenv("TRUTH_REDIS_KEY", "truth")

    truth = _load_truth(system_url, truth_key, service_name)

    components = truth.get("components") or {}
    comp = components.get(service_name) or {}
    if not comp:
        raise RuntimeError(f"component '{service_name}' not found in Truth document")

    # ---------------------------------------------------
    # 2) Heartbeat
    # ---------------------------------------------------
    hb_cfg = comp.get("heartbeat") or {}
    heartbeat = {
        "interval_sec": int(hb_cfg.get("interval_sec", 1)),
        "ttl_sec": int(hb_cfg.get("ttl_sec", 15)),
    }

    # ---------------------------------------------------
    # 3) Workflow & scheduler
    # ---------------------------------------------------
    base_workflow: Dict[str, Any] = comp.get("workflow") or {}

    # DEV OVERRIDE: MASSIVE_SYMBOL → limit symbols to one (or a comma list)
    massive_symbol_env = os.getenv("MASSIVE_SYMBOL", "").strip()
    if massive_symbol_env:
        # shallow copy so we don't mutate Truth
        workflow = dict(base_workflow)
        symbols = [s.strip() for s in massive_symbol_env.split(",") if s.strip()]
        workflow["symbols"] = symbols
        logutil.log(
            service_name,
            "INFO",
            "🎯",
            f"Overriding workflow.symbols from MASSIVE_SYMBOL={massive_symbol_env} → {symbols}",
        )
    else:
        workflow = base_workflow

    # Base cadence comes from Truth (poll_interval_sec, num_expirations)
    base_interval = float(workflow.get("poll_interval_sec", 10))
    base_exps = int(workflow.get("num_expirations", 5))

    # Scheduler allows overriding via env.
    # Honor legacy FAST_* / REST_* first (old dev pattern),
    # then MASSIVE_FAST_* / MASSIVE_REST_* (shell menu),
    # then fall back to Truth defaults.
    fast_num_env = (
        os.getenv("FAST_NUM_EXPIRATIONS")
        or os.getenv("MASSIVE_FAST_NUM_EXPIRATIONS")
        or ""
    )
    fast_interval_env = (
        os.getenv("FAST_INTERVAL_SECS")
        or os.getenv("MASSIVE_FAST_INTERVAL_SEC")
        or ""
    )
    rest_num_env = (
        os.getenv("REST_NUM_EXPIRATIONS")
        or os.getenv("MASSIVE_REST_NUM_EXPIRATIONS")
        or ""
    )
    rest_interval_env = (
        os.getenv("REST_INTERVAL_SECS")
        or os.getenv("MASSIVE_REST_INTERVAL_SEC")
        or ""
    )

    fast_num = int(fast_num_env) if fast_num_env else base_exps
    fast_interval = float(fast_interval_env) if fast_interval_env else base_interval

    # If rest_* not set, mirror fast lane by default
    rest_num = int(rest_num_env) if rest_num_env else fast_num
    rest_interval = float(rest_interval_env) if rest_interval_env else fast_interval

    max_inflight = int(os.getenv("MASSIVE_MAX_INFLIGHT", "6"))

    scheduler = {
        "fast_interval": fast_interval,
        "fast_num_expirations": fast_num,
        "rest_interval": rest_interval,
        "rest_num_expirations": rest_num,
        "max_inflight": max_inflight,
    }

    logutil.log(
        service_name,
        "INFO",
        "🧮",
        (
            "scheduler resolved: "
            f"0DTE={fast_num} exp(s) every {fast_interval}s, "
            f"rest={rest_num} exp(s) every {rest_interval}s, "
            f"max_inflight={max_inflight}"
        ),
    )

    # ---------------------------------------------------
    # 4) Paths (PYTHON + CHAIN_LOADER) and Redis URLs
    # ---------------------------------------------------
    # Project root: .../MarketSwarm
    service_root = Path(__file__).resolve().parent          # services/massive
    project_root = service_root.parent.parent               # MarketSwarm

    # Chain loader: prefer env override, else default to utils/massive_chain_loader.py
    default_chain_loader = project_root / "services" / "massive" / "utils" / "massive_chain_loader.py"
    chain_loader = os.getenv("MASSIVE_CHAIN_LOADER", str(default_chain_loader))

    # Python interpreter: prefer env override (shell script) else current interpreter
    python_bin = os.getenv("PYTHON_BIN", sys.executable)

    # Redis URL for market data
    redis_market_url = os.getenv("MARKET_REDIS_URL", "redis://127.0.0.1:6380")

    # ---------------------------------------------------
    # 5) API key & debug flags
    # ---------------------------------------------------
    api_key_env = workflow.get("api_key_env", "MASSIVE_API_KEY")
    api_key = os.getenv(api_key_env, "")

    debug_rest = os.getenv("MASSIVE_DEBUG_REST", "false").lower() == "true"
    debug_threads = os.getenv("MASSIVE_DEBUG_THREADS", "false").lower() == "true"

    cfg: Dict[str, Any] = {
        "service_name": service_name,
        "truth_url": system_url,
        "truth_key": truth_key,
        "truth_path": system_url,
        "truth": truth,
        "component": comp,
        "heartbeat": heartbeat,
        "workflow": workflow,
        "scheduler": scheduler,
        "redis_market_url": redis_market_url,
        "CHAIN_LOADER": chain_loader,
        "PYTHON": python_bin,
        "api_key": api_key,
        "debug_rest": debug_rest,
        "debug_threads": debug_threads,
    }

    logutil.log(
        service_name,
        "INFO",
        "✅",
        f"setup() built config for service='{service_name}'",
    )
    return cfg