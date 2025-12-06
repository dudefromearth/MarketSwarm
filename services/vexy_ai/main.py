#!/usr/bin/env python3

import asyncio
import os
from datetime import datetime, UTC
from typing import Any, Dict

import setup          # services/vexy_ai/setup.py
import heartbeat      # services/vexy_ai/heartbeat.py (generic async heartbeat)
from intel import orchestrator  # services/vexy_ai/intel/orchestrator.py

import logutil        # services/vexy_ai/logutil.py


SERVICE_NAME = os.getenv("SERVICE_ID", "vexy_ai")


# ------------------------------------------------------------
# Logging helper (wraps logutil)
# ------------------------------------------------------------
def log(status: str, message: str, emoji: str = "", component: str = SERVICE_NAME) -> None:
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
        heartbeat.start_heartbeat(
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
    # 1) Setup: load Truth, resolve component, build config
    log("INFO", "starting setup()", "⚙️")
    config: Dict[str, Any] = setup.setup(service_name=SERVICE_NAME)

    hb_cfg = config.get("heartbeat", {}) or {}
    hb_interval = hb_cfg.get("interval_sec", 10)
    truth_url = config.get("truth_redis_url")
    truth_key = config.get("truth_key")

    log("INFO", "setup completed, configuration ready", "✅")
    log(
        "OK",
        f"configuration loaded (truth={truth_url} key={truth_key}, hb_interval={hb_interval}s)",
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
            await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Use UTC for consistency with heartbeat
        ts = datetime.now(UTC).isoformat(timespec="seconds")
        print(f"[{ts}][{SERVICE_NAME}][INFO] 🛑 received Ctrl+C, shutting down gracefully")