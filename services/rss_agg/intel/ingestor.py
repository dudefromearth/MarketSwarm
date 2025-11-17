#!/usr/bin/env python3
import aiohttp
import asyncio
import feedparser
import hashlib
import time
import os
import json
import redis.asyncio as redis
from bs4 import BeautifulSoup


# ---- Simple HTML Helpers ----
async def fetch_html(session, url):
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                return await resp.text()
    except:
        pass
    return ""


def extract_abstract(html):
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for p in soup.find_all("p"):
            text = p.get_text().strip()
            if len(text) > 40:
                return text[:300]
    except:
        pass
    return "Full details at link."


# ---- Core Feed Processor ----
async def process_feed(r, session, category, feed_url, max_per_feed):
    try:
        async with session.get(feed_url, timeout=20) as resp:
            xml = await resp.text()
    except Exception as e:
        print(f"[Feed Error] {feed_url}: {e}")
        return

    feed = feedparser.parse(xml)

    for entry in feed.entries[:max_per_feed]:
        raw_uid = entry.get("id") or entry.get("link") or entry.get("title")
        if not raw_uid:
            continue

        uid = hashlib.sha1(raw_uid.encode()).hexdigest()

        # Dedup
        if await r.sismember("rss:seen", uid):
            continue

        # Fetch article page
        html = await fetch_html(session, entry.link)
        abstract = extract_abstract(html)

        # Store metadata
        item = {
            "uid": uid,
            "category": category,
            "title": entry.get("title", "Untitled"),
            "url": entry.get("link", ""),
            "abstract": abstract,
            "timestamp": time.time()
        }

        await r.hset(f"rss:item:{uid}", mapping=item)
        await r.zadd("rss:index", {uid: time.time()})
        await r.sadd("rss:seen", uid)

        # Push lightweight event for downstream
        await r.xadd("intel:rss:content", item)

        print(f"📰 Stored {uid[:8]} ({category})")


# ---- Top-Level ----
async def ingest_all():
    # redis connection
    host = os.getenv("INTEL_REDIS_HOST", "127.0.0.1")
    port = int(os.getenv("INTEL_REDIS_PORT", "6381"))
    r = redis.Redis(host=host, port=port, decode_responses=True)

    # feeds.json path
    root = os.getcwd()
    path = os.path.join(root, "services/rss_agg/schema/feeds.json")
    with open(path, "r") as f:
        cfg = json.load(f)

    feeds = cfg["feeds"]
    max_per_feed = cfg["workflow"].get("max_per_feed", 5)

    async with aiohttp.ClientSession() as session:
        for category, lst in feeds.items():
            print(f"\n📡 Category: {category}")
            for feed in lst:
                await process_feed(r, session, category, feed["url"], max_per_feed)

    print("\n✅ Ingestion complete.\n")


if __name__ == "__main__":
    asyncio.run(ingest_all())