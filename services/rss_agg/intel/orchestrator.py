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
    """Load feeds.json configuration file (auto-detect local or injected path)."""

    # 1️⃣ Check for env variable override
    feeds_path = os.getenv("FEEDS_CONFIG")
    if feeds_path and os.path.exists(feeds_path):
        print(f"📘 Loaded feeds.json from environment: {feeds_path}")
        with open(feeds_path, "r") as f:
            return json.load(f)

    # 2️⃣ Fallback to local schema directory
    local_path = os.path.join(os.getcwd(), "schema", "feeds.json")
    if os.path.exists(local_path):
        print(f"📘 Loaded feeds.json from local schema: {local_path}")
        with open(local_path, "r") as f:
            return json.load(f)

    # 3️⃣ Docker-era fallback (legacy)
    docker_path = "/app/schema/feeds.json"
    if os.path.exists(docker_path):
        print(f"📘 Loaded feeds.json from legacy Docker path: {docker_path}")
        with open(docker_path, "r") as f:
            return json.load(f)

    # 4️⃣ None found → explicit error
    raise FileNotFoundError(
        f"Missing feeds.json — checked:\n"
        f"  - FEEDS_CONFIG={feeds_path}\n"
        f"  - Local={local_path}\n"
        f"  - Docker={docker_path}"
    )


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
    redis_host = os.getenv("SYSTEM_REDIS_HOST", "127.0.0.1")
    redis_port = int(os.getenv("SYSTEM_REDIS_PORT", "6379"))
    print(f"[debug] Connecting to Redis host={redis_host} port={redis_port} for workflow...")

    try:
        r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        await r.ping()
        print(f"[debug] ✅ Connected to Redis at {redis_host}:{redis_port}")
    except Exception as e:
        raise ConnectionError(f"[Redis Error] Could not connect to Redis at {redis_host}:{redis_port} — {e}")

    schedule = feeds_conf["workflow"].get("schedule_sec", 600)
    print(f"🚀 Starting RSS Aggregation workflow for {svc}")
    print(f"⏱️  Fetch interval: {schedule} sec")

    while True:
        try:
            print("📡 Starting feed ingestion...")
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