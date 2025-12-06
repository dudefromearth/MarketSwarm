#!/usr/bin/env python3
"""
rss_agg/intel/orchestrator.py

New unified orchestrator for RSS Aggregator, adapted to the MarketSwarm
service pattern:

  - Async entrypoint: `async def run(config: Dict[str, Any])`
  - Uses logutil.log for all logging
  - Runs the existing synchronous pipeline (ingest → canonical → enrich
    → publish → stats) in a background thread via asyncio.to_thread,
    so heartbeat and orchestrator can coexist.

Expected config keys (from setup):
  - service_name: str               (e.g., "rss_agg")
  - truth: dict                     (composite Truth from Redis)
  - feeds_cfg: dict                 (parsed feeds.json)
  - intel_redis: { "host": str, "port": int }
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict

import redis

import logutil
from .ingestor import ingest_feeds
from .canonical_fetcher import canonical_fetcher_run_once
from .article_enricher import enrich_articles_lifo
from .publisher import generate_all_feeds
from .stats import generate_stats


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
            # fall through to env/default
            pass

    env_name = f"PIPELINE_{name.upper()}"
    env_val = os.getenv(env_name)
    if env_val is not None:
        return 1 if env_val.strip() == "1" else 0

    return 1 if default != 0 else 0


# -------------------------------------------------------------------
# Stage runners — synchronous, but log through logutil
# -------------------------------------------------------------------
def _run_ingest(service: str, feeds_cfg: Dict[str, Any]) -> None:
    logutil.log(service, "INFO", "📡", "INGEST: ingest_feeds()")
    ingest_feeds(feeds_cfg)
    logutil.log(service, "INFO", "✅", "INGEST: complete")


def _run_canonical(service: str) -> None:
    logutil.log(service, "INFO", "🧱", "CANONICAL: canonical_fetcher_run_once()")
    canonical_fetcher_run_once()
    logutil.log(service, "INFO", "✅", "CANONICAL: complete")


def _run_enrich(service: str) -> None:
    logutil.log(service, "INFO", "🧠", "ENRICH: enrich_articles_lifo()")
    enrich_articles_lifo()
    logutil.log(service, "INFO", "✅", "ENRICH: complete")


def _run_publish(service: str, publish_dir: str) -> None:
    logutil.log(service, "INFO", "📰", f"PUBLISH: generate_all_feeds() → {publish_dir}")
    generate_all_feeds(publish_dir)
    logutil.log(service, "INFO", "✅", "PUBLISH: complete")


def _run_stats(service: str) -> None:
    logutil.log(service, "INFO", "📊", "STATS: generate_stats()")
    generate_stats()
    logutil.log(service, "INFO", "✅", "STATS: complete")


# -------------------------------------------------------------------
# Optional ledger debug (kept for future use)
# -------------------------------------------------------------------
def _debug_ledger_state(service: str, r: redis.Redis) -> None:
    """
    Print ledger entries so the operator can see what categories
    have been published recently. Informational only.
    """
    logutil.log(service, "INFO", "📘", "Checking publish ledgers…")

    keys = r.keys("rss:publish_ledger:*")
    if not keys:
        logutil.log(service, "INFO", "ℹ️", "No ledger keys found")
        return

    for key in keys:
        # rss:publish_ledger:<category>
        parts = key.split(":", 2)
        category = parts[2] if len(parts) >= 3 else key
        latest = r.zrevrange(key, 0, 0, withscores=True)
        if latest:
            _, ts = latest[0]
            logutil.log(
                service,
                "INFO",
                "🧾",
                f"ledger[{category}]: last_publish_ts={ts}",
            )
        else:
            logutil.log(service, "INFO", "🧾", f"ledger[{category}]: (empty)")

    # Just informational; no return value


# -------------------------------------------------------------------
# Synchronous pipeline core (runs in a thread)
# -------------------------------------------------------------------
def _run_pipeline_forever(config: Dict[str, Any]) -> None:
    service_name = config.get("service_name", "rss_agg")

    truth: Dict[str, Any] = config.get("truth") or {}
    feeds_cfg: Dict[str, Any] = config.get("feeds_cfg") or {}
    intel_info: Dict[str, Any] = config.get("intel_redis") or {}

    if not truth:
        raise RuntimeError("rss_agg orchestrator: missing 'truth' in config")
    if not feeds_cfg:
        raise RuntimeError("rss_agg orchestrator: missing 'feeds_cfg' in config")
    if not intel_info:
        raise RuntimeError("rss_agg orchestrator: missing 'intel_redis' in config")

    # Resolve publish_dir from Truth: components[service].workflow.publish_dir
    components = truth.get("components", {})
    comp = components.get(service_name, {})
    workflow = comp.get("workflow", {})
    publish_dir = workflow.get("publish_dir")

    if not publish_dir:
        raise RuntimeError(
            f"rss_agg orchestrator: no 'workflow.publish_dir' configured "
            f"for component '{service_name}' in Truth"
        )

    # Connect to intel-redis (used both by stages & for switches)
    r = redis.Redis(
        host=intel_info["host"],
        port=intel_info["port"],
        decode_responses=True,
    )
    try:
        r.ping()
        logutil.log(
            service_name,
            "INFO",
            "🔌",
            f"connected to intel-redis {intel_info['host']}:{intel_info['port']}",
        )
    except Exception as e:
        raise ConnectionError(f"Could not connect to intel-redis: {e}") from e

    # Stage switches
    ingest_on = _flag(r, "INGEST", 1)
    canonical_on = _flag(r, "CANONICAL", 1)
    enrich_on = _flag(r, "ENRICH", 1)
    publish_on = _flag(r, "PUBLISH", 1)
    stats_on = _flag(r, "STATS", 1)

    logutil.log(
        service_name,
        "INFO",
        "⚙️",
        (
            "pipeline switches: "
            f"INGEST={ingest_on} CANONICAL={canonical_on} "
            f"ENRICH={enrich_on} PUBLISH={publish_on} STATS={stats_on}"
        ),
    )

    # MODE-specific one-off runs
    if PIPELINE_MODE == "ingest_only":
        if ingest_on:
            _run_ingest(service_name, feeds_cfg)
        return

    if PIPELINE_MODE == "canonical_only":
        if canonical_on:
            _run_canonical(service_name)
        return

    if PIPELINE_MODE == "enrich_only":
        if enrich_on:
            _run_enrich(service_name)
        return

    if PIPELINE_MODE == "publish_only":
        if publish_on:
            _run_publish(service_name, publish_dir)
        return

    if PIPELINE_MODE == "stats_only":
        if stats_on:
            _run_stats(service_name)
        return

    # FULL LOOP: run every 300s
    while True:
        logutil.log(
            service_name,
            "INFO",
            "🔥",
            f"FULL PIPELINE START (mode={PIPELINE_MODE}, force_ingest={FORCE_INGEST})",
        )

        if ingest_on:
            _run_ingest(service_name, feeds_cfg)

        if canonical_on:
            _run_canonical(service_name)

        if enrich_on:
            _run_enrich(service_name)

        if publish_on:
            # Optionally inspect ledger before publish
            _debug_ledger_state(service_name, r)
            _run_publish(service_name, publish_dir)

        if stats_on:
            _run_stats(service_name)

        logutil.log(
            service_name,
            "INFO",
            "🎉",
            "FULL PIPELINE CYCLE COMPLETE",
        )
        logutil.log(
            service_name,
            "INFO",
            "⏳",
            "sleeping 300 seconds before next cycle",
        )

        time.sleep(300)  # 5 minutes; runs in a background thread


# -------------------------------------------------------------------
# Async entrypoint (called from main.py)
# -------------------------------------------------------------------
async def run(config: Dict[str, Any]) -> None:
    """
    Async orchestrator entrypoint.

    - Called from main.py as: `await orchestrator.run(config)`
    - Wraps the synchronous pipeline loop in asyncio.to_thread so that
      heartbeat (async) and orchestrator can run concurrently.
    """
    service_name = config.get("service_name", "rss_agg")
    logutil.log(service_name, "INFO", "🚀", "orchestrator starting")

    try:
        await asyncio.to_thread(_run_pipeline_forever, config)
    except asyncio.CancelledError:
        logutil.log(service_name, "INFO", "🛑", "orchestrator cancelled (shutdown)")
        raise
    except Exception as e:
        logutil.log(service_name, "ERROR", "❌", f"orchestrator fatal error: {e}")
        raise
    finally:
        logutil.log(service_name, "INFO", "✅", "orchestrator exiting")