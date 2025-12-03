#!/usr/bin/env python3
"""
main.py — Massive Service Entrypoint

Orchestration flow:
- setup_environment() loads truth.json and builds cfg
- Heartbeat thread runs in the background
- Main loop schedules orchestrator cycles using cfg["scheduler"]:
    - fast lane (typically 0DTE) with small interval
    - rest lane (1–4DTE or more) with larger interval
- 0DTE lane always has precedence when both are due.
"""

import signal
import threading
import time
from datetime import datetime, timezone

from setup import setup_environment
from heartbeat import start_heartbeat
from intel.orchestrator import run_orchestrator


# Global stop flag, set by signal handler
STOP = False


def log(stage: str, emoji: str, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}][massive|{stage}]{emoji} {msg}")


def handle_signal(sig, frame) -> None:
    global STOP
    log("main", "🛑", f"Received signal {sig}, shutting down…")
    STOP = True


# Register signal handlers
signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def run() -> None:
    # ------------------------------------------------------------------
    # Setup / configuration
    # ------------------------------------------------------------------
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
        log(
            "main",
            "⚠️",
            f"{cfg['workflow']['api_key_env']} missing — market pulls may fail until set",
        )

    log("main", "🚀", "Massive service starting (market data engine)…")

    # ------------------------------------------------------------------
    # Heartbeat thread
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Scheduler configuration (0DTE vs rest)
    # ------------------------------------------------------------------
    scheduler = cfg.get("scheduler", {})
    wf = cfg["workflow"]

    fast_interval = float(
        scheduler.get("fast_interval", wf.get("poll_interval", 10))
    )
    fast_num = int(
        scheduler.get("fast_num_expirations", wf.get("num_expirations", 7))
    )

    rest_interval = float(
        scheduler.get("rest_interval", fast_interval)
    )
    rest_num = int(
        scheduler.get("rest_num_expirations", fast_num)
    )

    log(
        "main",
        "🧮",
        f"Scheduler: 0DTE={fast_num} exp(s) every {fast_interval}s, "
        f"rest={rest_num} exp(s) every {rest_interval}s",
    )

    # ------------------------------------------------------------------
    # Main scheduling loop — pipelined 0DTE launches
    # ------------------------------------------------------------------
    last_fast = 0.0
    last_rest = 0.0

    workers = []
    max_inflight = int(scheduler.get("max_inflight", 6))

    while not STOP:
        now = time.time()

        # Prune finished workers
        alive = []
        for t in workers:
            if t.is_alive():
                alive.append(t)
        workers = alive
        inflight = len(workers)

        # 1) Fast lane — 0DTE, fire every fast_interval even if others still running
        if now - last_fast >= fast_interval:
            if inflight < max_inflight:
                t = threading.Thread(
                    target=run_orchestrator,
                    args=(
                        cfg,
                        log,
                        lambda: STOP,
                        fast_num,
                        "0DTE",
                    ),
                    daemon=True,
                )
                t.start()
                workers.append(t)
                last_fast = now
            else:
                log(
                    "main",
                    "⚠️",
                    f"Max inflight cycles reached ({max_inflight}), "
                    "skipping new 0DTE launch this tick.",
                )

        # 2) Rest lane — optional, likely off for pure 0DTE instance
        if (
            rest_num > fast_num
            and (now - last_rest) >= rest_interval
            and not STOP
        ):
            if inflight < max_inflight:
                t = threading.Thread(
                    target=run_orchestrator,
                    args=(
                        cfg,
                        log,
                        lambda: STOP,
                        rest_num,
                        "1-4DTE",
                    ),
                    daemon=True,
                )
                t.start()
                workers.append(t)
                last_rest = now
            else:
                log(
                    "main",
                    "⚠️",
                    f"Max inflight cycles reached ({max_inflight}), "
                    "skipping new 1-4DTE launch this tick.",
                )

        time.sleep(0.05)

if __name__ == "__main__":
    run()