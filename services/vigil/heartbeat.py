#!/usr/bin/env python3
"""
Lightweight Vigil heartbeat emitter
"""

import time
from datetime import datetime, timezone


def start_heartbeat(r_system, service_id, interval_sec=5, ttl_sec=15, stop_flag=None, log=None):
    """
    Emits heartbeat keys on system-redis until stop_flag() returns True.
    """

    last = 0

    while not stop_flag():
        now = time.time()

        if now - last >= interval_sec:
            r_system.setex(
                f"{service_id}:heartbeat",
                ttl_sec,
                datetime.now(timezone.utc).isoformat()
            )

            if log:
                log("heartbeat", "❤️", "Heartbeat sent")

            last = now

        time.sleep(0.1)  # small yield for CPU