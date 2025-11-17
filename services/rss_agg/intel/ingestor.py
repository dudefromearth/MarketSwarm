#!/usr/bin/env python3
import aiohttp
import asyncio
import feedparser
import hashlib
import time
import os
import json
import redis.asyncio as redis
from urllib.parse import urlparse, parse_qs, unquote


# --------------------------------------------------------
# URL Unwrapper
# --------------------------------------------------------
def unwrap_redirect(url: str) -> str:
    if not url:
        return url

    u = url.lower()

    if "://www.google.com/url" in u:
        try:
            q = urlparse(url).query
            params = parse_qs(q)
            if "url" in params:
                return unquote(params["url"][0])
        except:
            pass

    if "/amp/" in u:
        return url.replace("/amp/", "/")

    if "redir.aspx" in u:
        try:
            q = urlparse(url).query
            params = parse_qs(q)
            if "url" in params:
                return unquote(params["url"][0])
        except:
            pass

    if "r.search.yahoo.com" in u:
        try:
            q = parse_qs(urlparse(url).query)
            if "p" in q:
                return unquote(q["p"][0])
        except:
            pass

    return url


# --------------------------------------------------------
# Core feed processor
# --------------------------------------------------------
async def process_feed(r, session, category, feed_url, max_per_feed):

    try:
        async with session.get(feed_url, timeout=20) as resp:
            xml = await resp.text()
    except Exception as e:
        print(f"[Feed Error] {feed_url}: {e}")
        return

    feed = feedparser.parse(xml)

    for entry in feed.entries[:max_per_feed]:

        raw_identifier = entry.get("id") or entry.get("link") or entry.get("title")
        clean_identifier = unwrap_redirect(raw_identifier)

        uid = hashlib.sha1(clean_identifier.encode()).hexdigest()

        # Dedup
        if await r.sismember("rss:seen", uid):
            continue

        raw_url = entry.get("link", "")
        clean_url = unwrap_redirect(raw_url)

        item = {
            "uid": uid,
            "category": category,
            "title": entry.get("title", "Untitled"),
            "url": clean_url,
            "timestamp": time.time()
        }

        # store raw RSS item
        await r.hset(f"rss:item:{uid}", mapping=item)
        await r.zadd("rss:index", {uid: item["timestamp"]})
        await r.sadd("rss:seen", uid)

        # push into raw fetch queue
        await r.xadd("rss:raw_fetch_queue", item)

        print(f"📰 New item {uid[:8]} ({category}) → queued for raw-fetch")


# --------------------------------------------------------
# Ingest all feeds
# --------------------------------------------------------
async def ingest_all():
    host = os.getenv("INTEL_REDIS_HOST", "127.0.0.1")
    port = int(os.getenv("INTEL_REDIS_PORT", 6381))
    r = redis.Redis(host=host, port=port, decode_responses=True)

    root = os.getcwd()
    path = os.path.join(root, "services/rss_agg/schema/feeds.json")
    with open(path, "r") as f:
        cfg = json.load(f)

    feeds = cfg["feeds"]
    max_per_feed = cfg["workflow"].get("max_per_feed", 5)

    async with aiohttp.ClientSession() as session:
        for category, feed_list in feeds.items():
            print(f"\n📡 Category: {category}")
            for feed in feed_list:
                await process_feed(r, session, category, feed["url"], max_per_feed)

    print("\n✅ Ingestion complete.\n")