#!/usr/bin/env python3
"""
run_scheduler.py — lightweight internal scheduler for rss_agg
Runs generate_rss.py every N seconds (default 900 = 15 min).
If Truth defines a schedule interval, it overrides the default.
"""

import time
import subprocess
import redis
import json
import sys
import traceback

DEFAULT_INTERVAL = 900  # 15 min


def get_interval_from_truth(r):
    """Try to get interval (in seconds) from Truth if defined."""
    try:
        truth = json.loads(r.get("truth:generate_rss") or "{}")
        interval = truth.get("schedule", {}).get("interval_sec")
        if interval and isinstance(interval, int) and interval > 0:
            print(f"[Truth] Using interval from Truth: {interval} seconds")
            return interval
    except Exception as e:
        print(f"[Warning] Failed to read interval from Truth: {e}")
    return DEFAULT_INTERVAL


def main():
    try:
        # Connect to System Redis (Main Redis)
        r = redis.Redis(host="localhost", port=6379, decode_responses=True)
        r.ping()
        print("[Scheduler] Connected to System Redis (6379)")
    except Exception as e:
        print(f"[Fatal] Redis connection failed: {e}")
        sys.exit(1)

    interval = get_interval_from_truth(r)
    print(f"[Scheduler] Starting loop — interval = {interval} seconds")

    while True:
        try:
            print("[Scheduler] Running generate_rss.py ...")
            subprocess.run(["python3", "/app/scripts/generate_rss.py"], check=True)
            print("[Scheduler] ✅ generate_rss completed successfully")

            # Update status in Truth
            r.hset(
                "truth:generate_rss:status",
                mapping={"last_run_ts": time.time(), "last_status": "success"},
            )

        except subprocess.CalledProcessError as e:
            print(f"[Error] generate_rss.py failed: {e}")
            traceback.print_exc()
            r.hset(
                "truth:generate_rss:status",
                mapping={"last_run_ts": time.time(), "last_status": "failed"},
            )

        except Exception as e:
            print(f"[Error] Unexpected scheduler error: {e}")
            traceback.print_exc()

        print(f"[Scheduler] Sleeping for {interval} seconds...\n")
        time.sleep(interval)


if __name__ == "__main__":
    main()