#!/usr/bin/env python3

import asyncio
import os
from datetime import datetime, UTC
from typing import Any, Dict

import setup                    # services/vigil/setup.py
import heartbeat                # services/vigil/heartbeat.py
from intel import orchestrator  # services/vigil/intel/orchestrator.py


SERVICE_NAME = os.getenv("SERVICE_ID", "vigil")

# Read debug flag once from env
DEBUG_ENABLED = os.getenv("DEBUG_VIGIL", "false").lower() == "true"


# ------------------------------------------------------------
# Logging helper
# ------------------------------------------------------------
def log(level: str, message: str, emoji: str = "", component: str = SERVICE_NAME) -> None:
    """
    Standard log line:
      [timestamp][component][LEVEL] emoji message

    DEBUG lines are suppressed unless DEBUG_VIGIL=true.
    """
    if level.upper() == "DEBUG" and not DEBUG_ENABLED:
        return

    ts = datetime.now(UTC).isoformat(timespec="seconds")
    emoji_part = f" {emoji}" if emoji else ""
    print(f"[{ts}][{component}][{level.upper()}]{emoji_part} {message}")


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

    # Wait for orchestrator to finish; heartbeat keeps pulsing until we cancel it.
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

    hb_cfg = config.get("heartbeat", {})
    hb_interval = hb_cfg.get("interval_sec", 10)
    truth_path = config.get("truth_path")

    log("INFO", "setup completed, configuration ready", "✅")
    log(
        "OK",
        f"configuration loaded (truth={truth_path}, hb_interval={hb_interval}s)",
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
        log("INFO", "received Ctrl+C, shutting down gracefully", "🛑")