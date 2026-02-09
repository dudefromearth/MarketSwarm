#!/usr/bin/env python3
"""
rss_agg/intel/orchestrator.py

RSS Aggregator orchestrator using the MarketSwarm service pattern.

Expected config keys (from SetupBase):
  - service_name: str
  - workflow: { publish_dir: str, interval_sec: int }
  - buses: { intel-redis: { url: str } }
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

import redis

from .ingestor import ingest_feeds

# Path to feeds.json (relative to this file)
FEEDS_JSON_PATH = Path(__file__).parent.parent / "schema" / "feeds.json"
from .canonical_fetcher import canonical_fetcher_run_once
from .article_enricher import enrich_articles_lifo
from .tier3_enricher import init_from_config as init_enricher
from .publisher import generate_all_feeds
from .stats import generate_stats


# -------------------------------------------------------------------
# Module-level logger and shutdown event (set by run())
# -------------------------------------------------------------------
_logger = None
_shutdown_event = None


def _log(level: str, message: str, emoji: str = "ℹ️"):
    """Internal logging helper that uses the module-level logger."""
    if _logger is None:
        print(f"[rss_agg][{level}]{emoji} {message}")
        return

    if level == "INFO":
        _logger.info(message, emoji=emoji)
    elif level == "WARN":
        _logger.warn(message, emoji=emoji)
    elif level == "ERROR":
        _logger.error(message, emoji=emoji)
    elif level == "DEBUG":
        _logger.debug(message, emoji=emoji)
    elif level == "OK":
        _logger.ok(message, emoji=emoji)
    else:
        _logger.info(message, emoji=emoji)


# -------------------------------------------------------------------
# Global pipeline mode
# -------------------------------------------------------------------
PIPELINE_MODE = os.getenv("PIPELINE_MODE", "full").lower()
FORCE_INGEST = os.getenv("FORCE_INGEST", "false").lower() == "true"


# -------------------------------------------------------------------
# Stage switch helper
# -------------------------------------------------------------------
def _flag(r: redis.Redis, name: str, default: int = 1) -> int:
    """
    Read pipeline stage switches with this precedence:
      1. Redis key: pipeline:switch:<name>
      2. Env var:   PIPELINE_<NAME>
      3. Default
    Returns 0 or 1.
    """
    redis_key = f"pipeline:switch:{name}"
    redis_val = r.get(redis_key)
    if redis_val is not None:
        try:
            value = int(redis_val)
            return 1 if value != 0 else 0
        except ValueError:
            pass

    env_name = f"PIPELINE_{name.upper()}"
    env_val = os.getenv(env_name)
    if env_val is not None:
        return 1 if env_val.strip() == "1" else 0

    return 1 if default != 0 else 0


# -------------------------------------------------------------------
# Stage runners
# -------------------------------------------------------------------
def _run_ingest(feeds_cfg: Dict[str, Any]) -> None:
    _log("INFO", "INGEST: ingest_feeds()", "📡")
    ingest_feeds(feeds_cfg)
    _log("INFO", "INGEST: complete", "✅")


def _run_canonical() -> None:
    _log("INFO", "CANONICAL: canonical_fetcher_run_once()", "🧱")
    canonical_fetcher_run_once()
    _log("INFO", "CANONICAL: complete", "✅")


def _run_enrich() -> None:
    _log("INFO", "ENRICH: enrich_articles_lifo()", "🧠")
    enrich_articles_lifo()
    _log("INFO", "ENRICH: complete", "✅")


def _run_publish(publish_dir: str) -> None:
    _log("INFO", f"PUBLISH: generate_all_feeds() → {publish_dir}", "📰")
    generate_all_feeds(publish_dir)
    _log("INFO", "PUBLISH: complete", "✅")


def _run_stats() -> None:
    _log("INFO", "STATS: generate_stats()", "📊")
    generate_stats()
    _log("INFO", "STATS: complete", "✅")


# -------------------------------------------------------------------
# Optional ledger debug
# -------------------------------------------------------------------
def _debug_ledger_state(r: redis.Redis) -> None:
    """Print ledger entries for operator visibility."""
    _log("INFO", "Checking publish ledgers…", "📘")

    keys = r.keys("rss:publish_ledger:*")
    if not keys:
        _log("INFO", "No ledger keys found", "ℹ️")
        return

    for key in keys:
        parts = key.split(":", 2)
        category = parts[2] if len(parts) >= 3 else key
        latest = r.zrevrange(key, 0, 0, withscores=True)
        if latest:
            _, ts = latest[0]
            _log("INFO", f"ledger[{category}]: last_publish_ts={ts}", "🧾")
        else:
            _log("INFO", f"ledger[{category}]: (empty)", "🧾")


# -------------------------------------------------------------------
# Synchronous pipeline core (runs in a thread)
# -------------------------------------------------------------------
def _run_pipeline_forever(config: Dict[str, Any]) -> None:
    # Initialize tier3 enricher with config (API keys from Truth)
    init_enricher(config)

    # Get workflow config
    workflow = config.get("workflow", {})
    publish_dir = workflow.get("publish_dir")
    interval_sec = workflow.get("interval_sec", 600)

    if not publish_dir:
        raise RuntimeError("rss_agg orchestrator: no 'workflow.publish_dir' in config")

    # Get feeds config (loaded by setup or from file)
    feeds_cfg = config.get("feeds_cfg", {})
    if not feeds_cfg and FEEDS_JSON_PATH.exists():
        _log("INFO", f"loading feeds from {FEEDS_JSON_PATH}", "📂")
        feeds_cfg = json.loads(FEEDS_JSON_PATH.read_text())

    # Connect to intel-redis
    buses = config.get("buses", {})
    intel_bus = buses.get("intel-redis", {})
    intel_url = intel_bus.get("url", "redis://127.0.0.1:6381")

    parsed = urlparse(intel_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6381

    r = redis.Redis(host=host, port=port, decode_responses=True)
    try:
        r.ping()
        _log("INFO", f"connected to intel-redis {host}:{port}", "🔌")
    except Exception as e:
        raise ConnectionError(f"Could not connect to intel-redis: {e}") from e

    # Stage switches
    ingest_on = _flag(r, "INGEST", 1)
    canonical_on = _flag(r, "CANONICAL", 1)
    enrich_on = _flag(r, "ENRICH", 1)
    publish_on = _flag(r, "PUBLISH", 1)
    stats_on = _flag(r, "STATS", 1)

    _log(
        "INFO",
        f"pipeline switches: INGEST={ingest_on} CANONICAL={canonical_on} "
        f"ENRICH={enrich_on} PUBLISH={publish_on} STATS={stats_on}",
        "⚙️",
    )

    # MODE-specific one-off runs
    if PIPELINE_MODE == "ingest_only":
        if ingest_on:
            _run_ingest(feeds_cfg)
        return

    if PIPELINE_MODE == "canonical_only":
        if canonical_on:
            _run_canonical()
        return

    if PIPELINE_MODE == "enrich_only":
        if enrich_on:
            _run_enrich()
        return

    if PIPELINE_MODE == "publish_only":
        if publish_on:
            _run_publish(publish_dir)
        return

    if PIPELINE_MODE == "stats_only":
        if stats_on:
            _run_stats()
        return

    # FULL LOOP
    while True:
        # Check for shutdown before starting a cycle
        if _shutdown_event and _shutdown_event.is_set():
            _log("INFO", "shutdown requested, exiting pipeline loop", "🛑")
            break

        _log("INFO", f"FULL PIPELINE START (mode={PIPELINE_MODE}, force_ingest={FORCE_INGEST})", "🔥")

        if ingest_on:
            _run_ingest(feeds_cfg)

        if canonical_on:
            _run_canonical()

        if enrich_on:
            _run_enrich()

        if publish_on:
            _debug_ledger_state(r)
            _run_publish(publish_dir)

        if stats_on:
            _run_stats()

        _log("INFO", "FULL PIPELINE CYCLE COMPLETE", "🎉")
        _log("INFO", f"sleeping {interval_sec} seconds before next cycle", "⏳")

        # Interruptible sleep - check shutdown every second
        for _ in range(interval_sec):
            if _shutdown_event and _shutdown_event.is_set():
                _log("INFO", "shutdown requested during sleep", "🛑")
                return
            time.sleep(1)


# -------------------------------------------------------------------
# Async entrypoint (called from main.py)
# -------------------------------------------------------------------
async def run(config: Dict[str, Any], logger=None, shutdown_event=None) -> None:
    """
    Async orchestrator entrypoint.

    - Called from main.py as: `await orchestrator.run(config, logger, shutdown_event)`
    - Wraps the synchronous pipeline loop in asyncio.to_thread
    - shutdown_event: threading.Event that signals graceful shutdown
    """
    global _logger, _shutdown_event
    _logger = logger
    _shutdown_event = shutdown_event

    _log("INFO", "orchestrator starting", "🚀")

    try:
        await asyncio.to_thread(_run_pipeline_forever, config)
    except asyncio.CancelledError:
        _log("INFO", "orchestrator cancelled (shutdown)", "🛑")
        raise
    except Exception as e:
        _log("ERROR", f"orchestrator fatal error: {e}", "❌")
        raise
    finally:
        _log("INFO", "orchestrator exiting", "✅")


def request_shutdown():
    """Request graceful shutdown of the orchestrator."""
    global _shutdown_event
    if _shutdown_event:
        _shutdown_event.set()
