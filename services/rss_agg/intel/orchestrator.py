#!/usr/bin/env python3
import asyncio
import json
import os
import time
import redis.asyncio as redis
from .ingestor import ingest_all_feeds
from .publisher import generate_all_feeds


# ---- Load Feeds Configuration ----
async def load_feeds_config():
    """Load feeds.json configuration file from /app/schema."""
    path = "/app/schema/feeds.json"
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing feeds.json at {path}")
    with open(path, "r") as f:
        config = json.load(f)
    print(f"📘 Loaded feeds.json with {len(config['feeds'])} categories.")
    return config


# ---- Scheduler ----
async def schedule_feed_generation(feeds_conf, interval_sec: int):
    """Periodically regenerate all RSS feeds from Redis."""
    while True:
        try:
            print("🧩 Generating all RSS feeds from Redis...")
            await asyncio.to_thread(generate_all_feeds, feeds_conf)
            print("✅ Feed generation complete.")
        except Exception as e:
            print(f"[Publisher Error] {e}")
        await asyncio.sleep(interval_sec)


# ---- Main Workflow ----
async def start_workflow(svc, feeds_conf):
    """Run the RSS ingestion loop with publishing and indexing."""
    r = redis.Redis(host="system-redis", port=6379, decode_responses=True)
    schedule = feeds_conf["workflow"].get("schedule_sec", 600)

    print(f"🚀 Starting RSS Aggregation workflow for {svc}")
    print(f"⏱️  Fetch interval: {schedule} sec")

    while True:
        try:
            await ingest_all_feeds(feeds_conf)
            await r.hset(
                "rss_agg:status",
                mapping={
                    "last_run_ts": time.time(),
                    "last_status": "success",
                },
            )
        except Exception as e:
            await r.hset(
                "rss_agg:status",
                mapping={
                    "last_run_ts": time.time(),
                    "last_status": f"failed: {e}",
                },
            )
            print(f"[RSS Agg Error] {e}")

        print(f"🕒 Sleeping for {schedule} seconds before next fetch...\n")
        await asyncio.sleep(schedule)


# ---- Orchestrator Entrypoint ----
async def run_orchestrator(svc):
    """Initialize the orchestrator for RSS Aggregator service."""
    print(f"🧠 Orchestrator initializing for {svc}...", flush=True)

    feeds_conf = await load_feeds_config()

    interval = feeds_conf["workflow"].get("schedule_sec", 600)

    print("⚙️  Launching ingestion + publishing loops...")
    await asyncio.gather(
        start_workflow(svc, feeds_conf),
        schedule_feed_generation(feeds_conf, interval)
    )