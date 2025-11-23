#!/usr/bin/env python3
"""
main.py — Content_Anal Service Entrypoint
"""

import time
import signal
import threading
from datetime import datetime, timezone

from setup import setup_environment
from heartbeat import start_heartbeat
from intel.orchestrator import run_orchestrator

STOP = False


def log(msg, emoji="🧠", stage="main"):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}][content_anal|{stage}]{emoji} {msg}")


def handle_signal(sig, frame):
    global STOP
    log(f"Received signal {sig}, shutting down…", "🛑")
    STOP = True


# Register shutdown handlers
signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def run():
    global STOP

    cfg = setup_environment()
    r_system = cfg["r_system"]
    SERVICE_ID = cfg["SERVICE_ID"]
    hb_cfg = cfg["component"]["heartbeat"]

    log("Content_Anal service starting…", "🚀")

    # ---------------------------------------------------------
    # Heartbeat thread (daemon, never joined — like Vigil)
    # ---------------------------------------------------------
    threading.Thread(
        target=lambda: start_heartbeat(
            r_system,
            SERVICE_ID,
            hb_cfg["interval_sec"],
            hb_cfg["ttl_sec"],
            stop_flag=lambda: STOP,
            log=lambda step, emo, msg: log(msg, emo, "heartbeat")
        ),
        daemon=True,   # CRITICAL FOR GRACEFUL SHUTDOWN
        name="heartbeat-thread"
    ).start()

    # ---------------------------------------------------------
    # Main orchestrator loop — must be short & non-blocking
    # ---------------------------------------------------------
    while not STOP:
        run_orchestrator(cfg)
        time.sleep(0.5)

    log("Content_Anal stopped cleanly.", "🙏")


if __name__ == "__main__":
    run()