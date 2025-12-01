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
    try:
        cfg = setup_environment()
    except RuntimeError as e:
        # Graceful startup failure with clear explanation
        log("main", "❌", f"Setup failed — {e}")
        log("main", "🙏", "Massive will not start until the issue above is resolved.")
        return

    r_system = cfg["r_system"]
    hb = cfg["heartbeat"]
    service_id = cfg["SERVICE_ID"]

    if not cfg.get("api_key"):
        log("main", "⚠️", "MASSIVE_API_KEY missing — market pulls will fail until set")

    log("main", "🚀", "Massive service starting (prototype market pull)…")

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