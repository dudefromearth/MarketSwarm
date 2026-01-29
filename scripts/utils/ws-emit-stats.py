#!/usr/bin/env python3
"""
ws-emit-stats.py — Analyze emit performance over time windows.

Usage:
    ./ws-emit-stats.py                    # Last 5 minutes
    ./ws-emit-stats.py --window 60        # Last 60 seconds
    ./ws-emit-stats.py --window 300       # Last 5 minutes
    ./ws-emit-stats.py --window 3600      # Last hour
    ./ws-emit-stats.py --buckets 1m       # Show per-minute breakdown
    ./ws-emit-stats.py --buckets 10s      # Show per-10-second breakdown
    ./ws-emit-stats.py --since 09:30      # Since market open (HH:MM)
    ./ws-emit-stats.py --until 10:00      # Until specific time
"""

import argparse
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

from redis.asyncio import Redis


async def fetch_emit_stream(r: Redis, start_ts: float, end_ts: float = None):
    """Fetch emit events from stream within time range."""
    # Convert to Redis stream IDs (millisecond timestamps)
    start_id = f"{int(start_ts * 1000)}-0"
    end_id = f"{int(end_ts * 1000)}-0" if end_ts else "+"

    results = await r.xrange("massive:ws:emit:stream", min=start_id, max=end_id)

    events = []
    for entry_id, fields in results:
        events.append({
            "id": entry_id,
            "ts": float(fields.get("ts", 0)),
            "diffs": int(fields.get("diffs", 0)),
            "contracts": int(fields.get("contracts", 0)),
        })
    return events


def parse_time(time_str: str) -> float:
    """Parse HH:MM or HH:MM:SS to today's timestamp."""
    today = datetime.now().date()
    parts = time_str.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    second = int(parts[2]) if len(parts) > 2 else 0
    dt = datetime(today.year, today.month, today.day, hour, minute, second)
    return dt.timestamp()


def parse_bucket_size(bucket_str: str) -> int:
    """Parse bucket size string to seconds."""
    if bucket_str.endswith("s"):
        return int(bucket_str[:-1])
    elif bucket_str.endswith("m"):
        return int(bucket_str[:-1]) * 60
    elif bucket_str.endswith("h"):
        return int(bucket_str[:-1]) * 3600
    return int(bucket_str)


def bucket_events(events, bucket_seconds: int):
    """Group events into time buckets."""
    buckets = defaultdict(list)
    for e in events:
        bucket_ts = int(e["ts"] / bucket_seconds) * bucket_seconds
        buckets[bucket_ts].append(e)
    return dict(sorted(buckets.items()))


def print_stats(events, label=""):
    """Print summary statistics for a set of events."""
    if not events:
        print(f"  No data{' for ' + label if label else ''}")
        return

    diffs = [e["diffs"] for e in events]

    total_diffs = sum(diffs)
    count = len(events)
    avg = total_diffs / count if count else 0

    print(f"  Emits: {count}")
    print(f"  Total diffs: {total_diffs}")
    print(f"  Avg diffs/emit: {avg:.2f}")

    if len(diffs) > 1:
        print(f"  Min/Max: {min(diffs)} / {max(diffs)}")
        print(f"  Std dev: {statistics.stdev(diffs):.2f}")

        # Percentiles
        sorted_diffs = sorted(diffs)
        p50 = sorted_diffs[len(sorted_diffs) // 2]
        p90 = sorted_diffs[int(len(sorted_diffs) * 0.9)]
        p99 = sorted_diffs[int(len(sorted_diffs) * 0.99)]
        print(f"  P50/P90/P99: {p50} / {p90} / {p99}")

    # Time span
    if events:
        duration = events[-1]["ts"] - events[0]["ts"]
        if duration > 0:
            hz = count / duration
            print(f"  Frequency: {hz:.2f} Hz ({1000/hz:.0f}ms avg interval)")

    # Zero-diff emits (wasted cycles)
    zero_count = sum(1 for d in diffs if d == 0)
    if zero_count > 0:
        print(f"  Zero-diff emits: {zero_count} ({100*zero_count/count:.1f}%) — potential to slow down")


async def main():
    parser = argparse.ArgumentParser(description="Analyze WS emit performance")
    parser.add_argument("--window", type=int, default=300, help="Time window in seconds (default: 300)")
    parser.add_argument("--since", type=str, help="Start time HH:MM")
    parser.add_argument("--until", type=str, help="End time HH:MM")
    parser.add_argument("--buckets", type=str, help="Bucket size (e.g., 10s, 1m, 5m)")
    args = parser.parse_args()

    r = Redis.from_url("redis://127.0.0.1:6380", decode_responses=True)

    now = datetime.now().timestamp()

    # Determine time range
    if args.since:
        start_ts = parse_time(args.since)
    else:
        start_ts = now - args.window

    end_ts = parse_time(args.until) if args.until else now

    events = await fetch_emit_stream(r, start_ts, end_ts)

    start_dt = datetime.fromtimestamp(start_ts).strftime("%H:%M:%S")
    end_dt = datetime.fromtimestamp(end_ts).strftime("%H:%M:%S")

    print(f"\n=== Emit Stats: {start_dt} to {end_dt} ===\n")
    print_stats(events)

    if args.buckets:
        bucket_sec = parse_bucket_size(args.buckets)
        bucketed = bucket_events(events, bucket_sec)

        print(f"\n=== Per-{args.buckets} Breakdown ===\n")
        print(f"{'Time':<12} {'Emits':>6} {'Diffs':>7} {'Avg':>6} {'Zero%':>6}")
        print("-" * 45)

        for bucket_ts, bucket_events_list in bucketed.items():
            time_str = datetime.fromtimestamp(bucket_ts).strftime("%H:%M:%S")
            emit_count = len(bucket_events_list)
            total_diffs = sum(e["diffs"] for e in bucket_events_list)
            avg = total_diffs / emit_count if emit_count else 0
            zero_pct = 100 * sum(1 for e in bucket_events_list if e["diffs"] == 0) / emit_count if emit_count else 0
            print(f"{time_str:<12} {emit_count:>6} {total_diffs:>7} {avg:>6.1f} {zero_pct:>5.0f}%")

    await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
