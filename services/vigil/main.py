#!/usr/bin/env python3
"""
main.py — Vigil Service Entrypoint (updated with proper heartbeat thread)
"""

import time
import signal
import threading
from datetime import datetime, timezone

from setup import setup_environment
from intel.event_watcher import run_once
from heartbeat import start_heartbeat

STOP = False

def banner(msg: str, emoji="🛡️", service="vigil"):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}][{service}|main]{emoji} {msg}")

def handle_signal(sig, frame):
    global STOP
    banner(f"Received signal {sig}, shutting down…", "🛑")
    STOP = True

# Register shutdown handlers
signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

def run():
    global STOP
    cfg = setup_environment()
    r_system = cfg["r_system"]
    SERVICE_ID = cfg["SERVICE_ID"]

    banner("Vigil service starting…", "🚀")

    # -----------------------------------------------------
    # Start heartbeat thread
    # -----------------------------------------------------
    threading.Thread(
        target=lambda: start_heartbeat(
            r_system,
            SERVICE_ID,
            interval_sec=5,
            ttl_sec=15,
            stop_flag=lambda: STOP,
            log=lambda step, emo, msg: banner(msg, emo)
        ),
        daemon=True
    ).start()

    # -----------------------------------------------------
    # Main watcher loop
    # -----------------------------------------------------
    while not STOP:
        run_once()
        time.sleep(0.2)

    banner("Vigil service stopped cleanly.", "🙏")

if __name__ == "__main__":
    run()