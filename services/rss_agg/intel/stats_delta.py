#!/usr/bin/env python3
import redis
import time

r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)

def window_count(key, hours):
    now = time.time()
    return r.zcount(key, now - hours * 3600, "+inf")

def show(key, label):
    last6  = window_count(key, 6)
    last12 = window_count(key, 12)
    last24 = window_count(key, 24)

    print(f"{label:15s}  6h={last6:4d}   12h={last12:4d}   24h={last24:4d}")

def main():
    print("\n────────── MarketSwarm Activity (Past 6 / 12 / 24 hours) ──────────\n")

    show("rss:stats:ingest:events",      "Ingested")
    show("rss:stats:raw:events",         "Raw Fetched")
    show("rss:stats:canonical:events",   "Canonicalized")
    show("rss:stats:enriched:events",    "Enriched")

    print("\n────────────────────────────────────────────────────────────────────\n")

if __name__ == "__main__":
    main()