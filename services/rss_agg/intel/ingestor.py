#!/usr/bin/env python3
import aiohttp
import asyncio
import feedparser
import hashlib
import time
import os
import redis.asyncio as redis
from bs4 import BeautifulSoup


# ---- HTML Fetch Helpers ----
async def fetch_html(session, url):
    """Fetch HTML content safely."""
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                return await resp.text()
    except Exception as e:
        print(f"[Fetch Error] {url}: {e}")
    return ""


def extract_main_image(html):
    """Try to extract main image (og:image, twitter:image, or first <img>)."""
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Try OpenGraph or Twitter cards first
        for prop in ["og:image", "twitter:image"]:
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                return tag["content"]

        # Fallback to first image in article content
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]

    except Exception as e:
        print(f"[Image Parse Error] {e}")
    return None


def extract_abstract(html):
    """Extract an abstract from the article text (first meaningful paragraph)."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        paragraphs = [p.get_text().strip() for p in soup.find_all("p") if len(p.get_text().strip()) > 40]
        if paragraphs:
            abstract = paragraphs[0]
            if len(abstract) > 300:
                abstract = abstract[:297].rsplit(" ", 1)[0] + "..."
            return abstract
    except Exception as e:
        print(f"[Abstract Parse Error] {e}")
    return "Full details at link."


# ---- Core Feed Processor ----
async def process_feed(r, session, category, feed_url, max_per_feed=5):
    """Fetch and store items from a single RSS feed."""
    try:
        async with session.get(feed_url, timeout=30) as resp:
            xml = await resp.text()
    except Exception as e:
        print(f"[Feed Error] {feed_url}: {e}")
        return

    feed = feedparser.parse(xml)
    for entry in feed.entries[:max_per_feed]:
        # Normalize UID
        raw_uid = entry.get("id") or entry.get("link") or entry.get("title")
        if not raw_uid:
            continue
        uid = hashlib.sha1(raw_uid.encode()).hexdigest()

        # Deduplication
        if await r.sismember("rss:seen", uid):
            continue

        # Fetch and parse full article
        html = await fetch_html(session, entry.link)
        image_url = extract_main_image(html)
        abstract = extract_abstract(html)

        # Store normalized data
        item = {
            "title": entry.get("title", "Untitled"),
            "url": entry.get("link", ""),
            "abstract": abstract,
            "category": category,
            "image": image_url or "",
            "timestamp": time.time(),
        }

        key = f"rss:item:{uid}"
        await r.hset(key, mapping=item)
        await r.zadd("rss:index", {uid: time.time()})
        await r.xadd("rss:queue", {"uid": uid, "title": item["title"], "image": item["image"]})
        await r.sadd("rss:seen", uid)

        print(f"📰 Stored {uid[:8]} in category {category} ({'🖼️' if image_url else '❌ no image'})")


# ---- Top-Level Ingestion ----
async def ingest_all_feeds(feeds_conf):
    """Fetch and store all RSS feeds into Redis."""
    redis_host = os.getenv("SYSTEM_REDIS_HOST", "localhost")
    redis_port = int(os.getenv("SYSTEM_REDIS_PORT", "6379"))
    print(f"[debug] Connecting to Redis host={redis_host} port={redis_port} for ingestion...")

    r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    feeds = feeds_conf.get("feeds", {})
    max_per_feed = feeds_conf["workflow"].get("max_per_feed", 5)

    async with aiohttp.ClientSession() as session:
        for category, feed_list in feeds.items():
            print(f"📡 Starting feed ingestion for category: {category}")
            for feed in feed_list:
                url = feed["url"]
                try:
                    await process_feed(r, session, category, url, max_per_feed)
                except Exception as e:
                    print(f"[Feed Error] {url}: {e}")

    print("✅ Feed ingestion complete.\n")