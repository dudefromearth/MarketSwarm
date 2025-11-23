# heartbeat.py
import time
from datetime import datetime, timezone

def start_heartbeat(r_system, service_id, interval_sec, ttl_sec, stop_flag, log):
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
        time.sleep(0.1)
