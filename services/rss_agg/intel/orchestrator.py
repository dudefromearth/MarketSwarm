#!/usr/bin/env python3
import asyncio
import json
import os
import time
import redis.asyncio as redis

from .ingestor import ingest_all
from .publisher import generate_all_feeds
from .article_ingestor import enrich_articles


# ------------------------------------------------------------
# Load Feeds Configuration
# ------------------------------------------------------------
async def load_feeds_config():
    """Load feeds.json configuration file."""
    feeds_path = os.getenv("FEEDS_CONFIG")

    if feeds_path and os.path.exists(feeds_path):
        print(f"📘 Loaded feeds.json from environment: {feeds_path}")
        with open(feeds_path, "r") as f:
            return json.load(f)

    local_path = os.path.join(os.getcwd(), "schema", "feeds.json")
    if os.path.exists(local_path):
        print(f"📘 Loaded feeds.json from local schema: {local_path}")
        with open(local_path, "r") as f:
            return json.load(f)

    docker_path = "/app/schema/feeds.json"
    if os.path.exists(docker_path):
        print(f"📘 Loaded feeds.json from docker schema: {docker_path}")
        with open(docker_path, "r") as f:
            return json.load(f)

    raise FileNotFoundError("❌ feeds.json not found in expected locations.")


# ------------------------------------------------------------
# Publisher Scheduler
# ------------------------------------------------------------
async def schedule_feed_generation(feeds_conf, interval_sec: int, truth):
    """Periodically regenerate all RSS feeds."""
    while True:
        try:
            print("🧩 Generating all RSS feeds from Redis...")
            await asyncio.to_thread(generate_all_feeds, feeds_conf, truth)
            print("✅ Feed generation complete.")
        except Exception as e:
            print(f"[Publisher Error] {e}")

        await asyncio.sleep(interval_sec)


# ------------------------------------------------------------
# Article Enrichment Scheduler
# ------------------------------------------------------------
async def schedule_article_enrichment(interval_sec: int):
    """Enrich RSS items into full articles & publish to vexy:intake."""
    while True:
        try:
            print("📝 Starting article enrichment...")
            await enrich_articles()  # ✔️ no truth argument
            print("✨ Article enrichment loop complete.")
        except Exception as e:
            print(f"[Enrichment Error] {e}")

        await asyncio.sleep(interval_sec)


# ------------------------------------------------------------
# Primary Ingest Workflow (fetch RSS → items)
# ------------------------------------------------------------
async def start_workflow(svc, feeds_conf):
    """Ingest RSS feeds & update status."""
    redis_host = os.getenv("SYSTEM_REDIS_HOST", "127.0.0.1")
    redis_port = int(os.getenv("SYSTEM_REDIS_PORT", "6379"))

    print(f"[debug] Connecting to Redis host={redis_host} port={redis_port} for workflow...")

    try:
        r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        await r.ping()
        print(f"[debug] ✅ Connected to Redis at {redis_host}:{redis_port}")
    except Exception as e:
        raise ConnectionError(f"[Redis Error] Could not connect to Redis: {e}")

    interval = feeds_conf["workflow"].get("schedule_sec", 600)

    print(f"🚀 Starting RSS ingest workflow for {svc}")
    print(f"⏱️ Fetch interval: {interval} sec")

    while True:
        try:
            print("📡 Starting feed ingestion...")
            await ingest_all()

            await r.hset(
                "rss_agg:status",
                mapping={
                    "last_run_ts": time.time(),
                    "last_status": "success"
                }
            )

        except Exception as e:
            await r.hset(
                "rss_agg:status",
                mapping={
                    "last_run_ts": time.time(),
                    "last_status": f"failed: {e}"
                }
            )
            print(f"[RSS Agg Error] {e}")

        print(f"🕒 Sleeping for {interval} sec...\n")
        await asyncio.sleep(interval)


# ------------------------------------------------------------
# Orchestrator Entrypoint
# ------------------------------------------------------------
async def run_orchestrator(svc: str, setup_info: dict, truth: dict):
    print(f"[orchestrator:init] 🧠 Starting orchestrator for {svc}")

    feeds_cfg = setup_info["feeds_cfg"]
    intel_info = setup_info["intel_redis"]

    interval = feeds_cfg["workflow"].get("schedule_sec", 600)

    # Validate intel-redis is reachable
    r_intel = redis.Redis(
        host=intel_info["host"],
        port=intel_info["port"],
        decode_responses=True
    )
    await r_intel.ping()

    print(f"[orchestrator] [ok] Connected to intel-redis at {intel_info['host']}:{intel_info['port']}")

    # Launch all loops concurrently
    await asyncio.gather(
        start_workflow(svc, feeds_cfg),                # Ingest RSS → rss:item
        schedule_article_enrichment(90),               # Enrich → vexy:intake
        schedule_feed_generation(feeds_cfg, interval, truth)  # Publish RSS feeds
    )