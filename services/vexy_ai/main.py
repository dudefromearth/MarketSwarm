#!/usr/bin/env python3
import signal
import threading
import time
from datetime import datetime, timezone

from setup import setup_service_environment
from intel.orchestrator import run_orchestrator
from heartbeat import start_heartbeat

# ---------------------------------------------------------
# Global shutdown flag
# ---------------------------------------------------------
stop_requested = False


# ---------------------------------------------------------
# Signal handler
# ---------------------------------------------------------
def handle_signal(sig, frame):
    global stop_requested
    stop_requested = True
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}][vexy_ai|main]🛑 Received signal {sig}, shutting down…")


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------
def main():
    global stop_requested

    svc = "vexy_ai"
    setup_info = setup_service_environment(svc)
    truth = setup_info["truth"]

    # Register signals
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Start heartbeat in background
    hb_thread = threading.Thread(
        target=lambda: start_heartbeat(svc, truth),
        daemon=True
    )
    hb_thread.start()

    print(f"[vexy_ai] 🚀 Vexy AI Play-by-Play Engine starting…")

    # -----------------------------------------------------
    # Run orchestrator loop until shutdown is requested
    # -----------------------------------------------------
    try:
        while not stop_requested:
            run_orchestrator(svc, setup_info, truth)
            # run_orchestrator normally loops inside,
            # but if it ever returns, we guard here.
            time.sleep(0.5)

    except Exception as e:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"[{ts}][vexy_ai|main]🔥 Fatal error in orchestrator: {e}")

    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}][vexy_ai|main]👋 Shutdown complete.")


if __name__ == "__main__":
    main()