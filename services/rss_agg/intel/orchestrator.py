#!/usr/bin/env python3
import asyncio
import json
import os
import time

import redis.asyncio as redis

# Primary ingestor
from .ingestor import ingest_feeds

# Publisher (now takes publish_dir only)
from .publisher import generate_all_feeds

# Enrichment + raw fetch + canonical
from .article_ingestor import enrich_articles
from .article_fetcher import fetch_and_store_article
from .canonical_fetcher import canonical_fetcher_run_once
from .article_enricher import enrich_articles_lifo


# ------------------------------------------------------------
# Pipeline mode switch
# ------------------------------------------------------------
PIPELINE_MODE = os.getenv("PIPELINE_MODE", "full").lower()


# ------------------------------------------------------------
# Load feeds.json
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
# Publisher Scheduler (fixed)
# ------------------------------------------------------------
async def schedule_feed_generation(publish_dir: str, interval_sec: int):
    """
    publish_dir comes from truth.json, not feeds.json.
    """
    while True:
        try:
            print(f"🧩 Generating all RSS feeds into: {publish_dir}")
            await asyncio.to_thread(generate_all_feeds, publish_dir)
            print("✅ Feed generation complete.")
        except Exception as e:
            print(f"[Publisher Error] {e}")

        await asyncio.sleep(interval_sec)


# ------------------------------------------------------------
# Canonical Fetcher Scheduler
# ------------------------------------------------------------
async def schedule_canonical_fetcher(interval_sec: int = 300):
    print(f"[canon_sched] 🚀 Canonical fetch scheduler every {interval_sec}s")
    while True:
        try:
            print("[canon_sched] 🔁 Running canonical_fetcher_run_once()")
            await canonical_fetcher_run_once()
        except Exception as e:
            print(f"[canon_sched] 🔥 Error: {e}")

        print(f"[canon_sched] ⏳ Sleeping {interval_sec}s")
        await asyncio.sleep(interval_sec)


# ------------------------------------------------------------
# Raw Fetch (legacy)
# ------------------------------------------------------------
async def schedule_article_fetching(interval_sec: int = 45):
    r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)
    print(f"[article_raw] 🚀 Raw fetcher (interval={interval_sec}s)")

    while True:
        try:
            uids = await r.zrevrange("rss:index", 0, 50)

            if not uids:
                print("[article_raw] 💤 No items in rss:index")
                await asyncio.sleep(interval_sec)
                continue

            for uid in uids:
                item_key = f"rss:item:{uid}"
                raw_key = f"rss:article_raw:{uid}"

                if await r.exists(raw_key):
                    continue

                item = await r.hgetall(item_key)
                if not item:
                    continue

                url = item.get("url")
                if not url:
                    continue

                print(f"[article_raw] 🌐 Fetching {uid[:8]} → {url}")

                await fetch_and_store_article(
                    uid=uid,
                    url=url,
                    title=item.get("title", ""),
                    category=item.get("category", ""),
                    r_intel=r,
                )

            await asyncio.sleep(interval_sec)

        except Exception as e:
            print(f"[article_raw] 🔥 Error: {e}")
            await asyncio.sleep(interval_sec)


# ------------------------------------------------------------
# Enrichment Stage
# ------------------------------------------------------------
async def schedule_article_enrichment(interval_sec: int):
    while True:
        try:
            print("[enrich] 📝 Running enrichment cycle…")
            await enrich_articles()
        except Exception as e:
            print(f"[Enrichment Error] {e}")

        await asyncio.sleep(interval_sec)


# ------------------------------------------------------------
# Tier-1 Ingestor (RSS → URLs)
# ------------------------------------------------------------
async def start_workflow(svc, feeds_conf):
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
    print(f"⏱️ Every {interval}s")

    while True:
        try:
            print("📡 Starting feed ingestion…")
            await ingest_feeds(feeds_conf)

            await r.hset("rss_agg:status", mapping={
                "last_run_ts": time.time(),
                "last_status": "success",
            })

        except Exception as e:
            await r.hset("rss_agg:status", mapping={
                "last_run_ts": time.time(),
                "last_status": f"failed: {e}",
            })
            print(f"[RSS Agg Error] {e}")

        await asyncio.sleep(interval)


# ------------------------------------------------------------
# ORCHESTRATOR ENTRYPOINT
# ------------------------------------------------------------
async def run_orchestrator(svc: str, setup_info: dict, truth: dict):
    print(f"[orchestrator:init] 🧠 Orchestrator starting ({PIPELINE_MODE})")

    feeds_cfg = setup_info["feeds_cfg"]
    intel_info = setup_info["intel_redis"]

    # Pull publisher directory from truth.json
    publish_dir = (
        truth["components"][svc]["workflow"]["publish_dir"]
    )

    # Interval still comes from feeds_cfg
    interval = feeds_cfg["workflow"].get("schedule_sec", 600)

    # Validate intel redis
    r_intel = redis.Redis(
        host=intel_info["host"],
        port=intel_info["port"],
        decode_responses=True,
    )
    await r_intel.ping()

    print(f"[orchestrator] [ok] Connected to intel-redis at "
          f"{intel_info['host']}:{intel_info['port']}")

    # --------------------- MODES ---------------------

    if PIPELINE_MODE == "ingest_only":
        print("[orchestrator] 🔬 Ingest-only")
        await asyncio.gather(start_workflow(svc, feeds_cfg))
        return

    if PIPELINE_MODE == "canonical_only":
        print("[orchestrator] 🔬 Canonical-only")
        await asyncio.gather(schedule_canonical_fetcher(300))
        return

    if PIPELINE_MODE == "fetch_only":
        print("[orchestrator] 🔬 Raw fetch-only")
        await asyncio.gather(schedule_article_fetching(30))
        return

    if PIPELINE_MODE == "enrich_only":
        print("[orchestrator] 🔬 Enrichment-only")
        await asyncio.gather(enrich_articles_lifo(30))
        return

    if PIPELINE_MODE == "publish_only":
        print("[orchestrator] 🔬 Publish-only")
        await asyncio.gather(
            schedule_feed_generation(publish_dir, interval)
        )
        return

    # ---------------- FULL PIPELINE ------------------

    print("[orchestrator] 🚀 FULL PIPELINE MODE")

    await asyncio.gather(
        start_workflow(svc, feeds_cfg),               # Step 1
        schedule_canonical_fetcher(300),              # Step 2
        schedule_article_fetching(30),                # Step 3
        enrich_articles_lifo(30),                     # Step 4
        schedule_feed_generation(publish_dir, interval),  # Step 5 (FIXED)
    )