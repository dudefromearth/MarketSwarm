#!/usr/bin/env python3
import asyncio
import json
import os
import time
import redis.asyncio as redis

from .ingestor import ingest_all
from .publisher import generate_all_feeds
from .article_ingestor import enrich_articles
from .article_fetcher import fetch_and_store_article   # ✅ NEW IMPORT


# ------------------------------------------------------------
# Load Feeds Configuration
# ------------------------------------------------------------
async def load_feeds_config():
    feeds_path = os.getenv("FEEDS_CONFIG")

    if feeds_path and os.path.exists(feeds_path):
        print(f"📘 Loaded feeds.json from env: {feeds_path}")
        with open(feeds_path, "r") as f:
            return json.load(f)

    local_path = os.path.join(os.getcwd(), "schema", "feeds.json")
    if os.path.exists(local_path):
        print(f"📘 Loaded feeds.json from local: {local_path}")
        with open(local_path, "r") as f:
            return json.load(f)

    docker_path = "/app/schema/feeds.json"
    if os.path.exists(docker_path):
        print(f"📘 Loaded feeds.json from docker: {docker_path}")
        with open(docker_path, "r") as f:
            return json.load(f)

    raise FileNotFoundError("❌ feeds.json not found.")


# ------------------------------------------------------------
# Publisher Scheduler
# ------------------------------------------------------------
async def schedule_feed_generation(feeds_conf, interval_sec: int, truth):
    while True:
        try:
            print("🧩 Generating all RSS feeds from Redis...")
            await asyncio.to_thread(generate_all_feeds, feeds_conf, truth)
            print("✅ Feed generation complete.")
        except Exception as e:
            print(f"[Publisher Error] {e}")

        await asyncio.sleep(interval_sec)


# ------------------------------------------------------------
# NEW: Raw Article Fetching Stage
# ------------------------------------------------------------
async def schedule_article_fetching(interval_sec: int = 45):
    """
    Fetch raw HTML for rss:item:* entries → store as rss:article_raw:{uid}.
    Enrichment happens in the next stage.
    """

    r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)
    print(f"[article_raw] 🚀 Raw article fetch loop started (interval={interval_sec}s)")

    while True:
        try:
            uids = await r.zrevrange("rss:index", 0, 50)

            if not uids:
                print("[article_raw] 💤 No items in rss:index")
                await asyncio.sleep(interval_sec)
                continue

            for uid in uids:
                raw_key = f"rss:item:{uid}"
                html_key = f"rss:article_raw:{uid}"

                # Skip if raw html already stored
                if await r.exists(html_key):
                    continue

                item = await r.hgetall(raw_key)
                if not item:
                    continue

                url = item.get("url", "")
                if not url:
                    continue

                print(f"[article_raw] 🌐 Fetching raw article {uid[:8]} → {url}")

                # Perform fetch (in article_fetcher.py)
                await fetch_and_store_article(
                    uid=uid,
                    url=url,
                    title=item.get("title", ""),
                    category=item.get("category", ""),
                    r_intel=r
                )

            print(f"[article_raw] ⏳ Sleeping {interval_sec}s")
            await asyncio.sleep(interval_sec)

        except Exception as e:
            print(f"[article_raw] 🔥 Error: {e}")
            await asyncio.sleep(interval_sec)


# ------------------------------------------------------------
# Enrichment Scheduler
# ------------------------------------------------------------
async def schedule_article_enrichment(interval_sec: int):
    while True:
        try:
            print("📝 Starting article enrichment...")
            await enrich_articles()
            print("✨ Article enrichment complete.")
        except Exception as e:
            print(f"[Enrichment Error] {e}")

        await asyncio.sleep(interval_sec)


# ------------------------------------------------------------
# Primary Ingest Workflow (RSS → items)
# ------------------------------------------------------------
async def start_workflow(svc, feeds_conf):
    """Fetch RSS feeds & write rss:item:{uid} into intel-redis."""

    redis_host = os.getenv("SYSTEM_REDIS_HOST", "127.0.0.1")
    redis_port = int(os.getenv("SYSTEM_REDIS_PORT", "6379"))

    print(f"[debug] Connecting to Redis {redis_host}:{redis_port}")

    try:
        r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        await r.ping()
        print(f"[debug] ✅ Connected to Redis {redis_host}:{redis_port}")
    except Exception as e:
        raise ConnectionError(f"[Redis Error] Could not connect: {e}")

    interval = feeds_conf["workflow"].get("schedule_sec", 600)

    print(f"🚀 Starting RSS ingest workflow for {svc}")
    print(f"⏱️ Fetch interval: {interval} sec")

    while True:
        try:
            print("📡 Starting feed ingestion...")
            await ingest_all()

            await r.hset("rss_agg:status", mapping={
                "last_run_ts": time.time(),
                "last_status": "success"
            })

        except Exception as e:
            await r.hset("rss_agg:status", mapping={
                "last_run_ts": time.time(),
                "last_status": f"failed: {e}"
            })
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

    # Validate intel-redis connectivity
    r_intel = redis.Redis(
        host=intel_info["host"],
        port=intel_info["port"],
        decode_responses=True
    )
    await r_intel.ping()

    print(f"[orchestrator] [ok] Connected to intel-redis at "
          f"{intel_info['host']}:{intel_info['port']}")

    # Start all parallel pipeline stages
    await asyncio.gather(
        start_workflow(svc, feeds_cfg),                   # RSS → items
        schedule_article_fetching(30),                    # NEW: fetch raw articles
        schedule_article_enrichment(90),                  # raw → enriched
        schedule_feed_generation(feeds_cfg, interval, truth)  # publish RSS feeds
    )

    from .raw_fetch_loop import raw_fetch_loop
    from .ingestor import ingest_all
    from .publisher import generate_all_feeds
    from .enrich_articles import enrich_articles

    async def run_orchestrator(svc, setup_info, truth):
        feeds_cfg = setup_info["feeds_cfg"]
        interval = feeds_cfg["workflow"].get("schedule_sec", 600)

        print("[orchestrator] starting…")

        await asyncio.gather(
            start_workflow(svc, feeds_cfg),  # ingest RSS → queue
            raw_fetch_loop(),  # continuous browser fetch
            schedule_article_enrichment(30),  # build full article
            schedule_feed_generation(feeds_cfg, interval, truth)
        )