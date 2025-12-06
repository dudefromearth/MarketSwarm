#!/usr/bin/env python3
"""
main.py — Canonical entry for RSS Aggregator (rss_agg).

Pattern:
  - Discover service id (SERVICE_ID or default 'rss_agg')
  - Call setup.setup() to load Truth from Redis and build config
  - Start heartbeat + orchestrator in a loop
  - Log in a consistent MarketSwarm format via logutil
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any, Dict

import setup                    # services/rss_agg/setup.py
from intel import orchestrator  # services/rss_agg/intel/orchestrator.py
from heartbeat import start_heartbeat  # services/rss_agg/heartbeat.py
import logutil                  # services/rss_agg/logutil.py


SERVICE_NAME = os.getenv("SERVICE_ID", "rss_agg")


# ------------------------------------------------------------
# Logging helper (wrapper around logutil)
# ------------------------------------------------------------
def log(status: str, message: str, emoji: str = "", component: str = SERVICE_NAME) -> None:
    """
    Standard log line:
      [timestamp][component][STATUS] emoji message
    """
    # Delegate to shared logutil so all services look the same
    logutil.log(component, status, emoji, message)


# ------------------------------------------------------------
# Single service cycle: heartbeat + orchestrator
# ------------------------------------------------------------
async def run_once(config: Dict[str, Any]) -> None:
    """
    Start heartbeat in the background and run orchestrator once.
    If orchestrator returns, we cancel heartbeat and return to caller.
    """
    log("INFO", "starting heartbeat + orchestrator", "🟢")

    hb_task = asyncio.create_task(
        start_heartbeat(
            service_name=SERVICE_NAME,
            config=config,
        ),
        name=f"{SERVICE_NAME}-heartbeat",
    )

    orch_task = asyncio.create_task(
        orchestrator.run(config),
        name=f"{SERVICE_NAME}-orchestrator",
    )

    try:
        # Wait for orchestrator to finish; heartbeat keeps pulsing until we cancel it
        await orch_task
        log("INFO", "orchestrator run() returned, cancelling heartbeat", "↩️")
    finally:
        if not hb_task.done():
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass


# ------------------------------------------------------------
# Main loop
# ------------------------------------------------------------
async def main() -> None:
    # 1) Setup: load Truth from Redis, resolve component, build config
    log("INFO", "starting setup()", "⚙️")
    config: Dict[str, Any] = setup.setup(service_name=SERVICE_NAME)

    hb_cfg = config.get("heartbeat", {}) or {}
    hb_interval = hb_cfg.get("interval_sec", 10)

    # Truth location reporting – this is what was previously cosmetic-busted
    truth_source = config.get("truth_source", {}) or {}
    truth_path = truth_source.get("path")
    truth_redis_url = truth_source.get("redis_url")
    truth_key = truth_source.get("key")

    if truth_path:
        truth_location = truth_path
    elif truth_redis_url and truth_key:
        truth_location = f"{truth_redis_url} key={truth_key}"
    elif truth_redis_url:
        truth_location = truth_redis_url
    else:
        truth_location = "unknown"

    log("INFO", "setup completed, configuration ready", "✅")
    log(
        "OK",
        f"configuration loaded (truth={truth_location}, hb_interval={hb_interval}s)",
        "📄",
    )

    # 2) Forever loop: run orchestrator + heartbeat, restart orchestrator when it returns
    log("INFO", "entering service loop (Ctrl+C to exit)", "♻️")

    while True:
        try:
            await run_once(config)
            # Orchestrator returned; log and immediately loop again
            log("INFO", "orchestrator cycle finished; restarting", "🔁")
        except asyncio.CancelledError:
            log("WARN", "service loop cancelled", "⚠️")
            break
        except Exception as e:
            log("ERROR", f"unhandled error in service loop: {e}", "💥")
            # Small backoff to avoid hot-spin if something is badly wrong.
            await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("INFO", "received Ctrl+C, shutting down gracefully", "🛑")