# main.py
#!/usr/bin/env python3
"""
main.py — Massive Service Entrypoint
"""
import time
import signal
import threading
from datetime import datetime, timezone

from setup import setup_environment
from heartbeat import start_heartbeat
from intel.orchestrator import run_orchestrator

STOP = False

def log(stage, emoji, msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}][massive|{stage}]{emoji} {msg}")

def handle_signal(sig, frame):
    global STOP
    log("main", "🛑", f"Received signal {sig}, shutting down…")
    STOP = True

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

def run():
    cfg = setup_environment()
    r_system = cfg["r_system"]
    comp = cfg["component"]
    hb = comp["heartbeat"]
    service_id = cfg["SERVICE_ID"]

    log("main", "🚀", "Massive service starting…")

    # Heartbeat thread
    threading.Thread(
        target=lambda: start_heartbeat(
            r_system,
            service_id,
            hb["interval_sec"],
            hb["ttl_sec"],
            stop_flag=lambda: STOP,
            log=log,
        ),
        daemon=True,
    ).start()

    while not STOP:
        run_orchestrator(cfg, log, lambda: STOP)
        time.sleep(1)

    log("main", "🙏", "Massive stopped cleanly.")

if __name__ == "__main__":
    run()