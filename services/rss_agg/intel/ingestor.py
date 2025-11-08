#!/usr/bin/env python3
import aiohttp
import asyncio
import feedparser
import hashlib
import time
import redis.asyncio as redis
from bs4 import BeautifulSoup


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
            # Return first paragraph with intelligent truncation
            abstract = paragraphs[0]
            if len(abstract) > 300:
                abstract = abstract[:297].rsplit(" ", 1)[0] + "..."
            return abstract
    except Exception as e:
        print(f"[Abstract Parse Error] {e}")
    return "Full details at link."


async def process_feed(r, session, cat, feed_url, max_per_feed=5):
    """Fetch a single feed and store items in Redis."""
    try:
        async with session.get(feed_url, timeout=10) as resp:
            xml = await resp.text()
    except Exception as e:
        print(f"[Feed Error] {feed_url}: {e}")
        return

    feed = feedparser.parse(xml)
    for entry in feed.entries[:max_per_feed]:
        uid = hashlib.sha1(entry.link.encode()).hexdigest()
        if await r.sismember("rss:seen", uid):
            continue

        # Fetch full article HTML
        html = await fetch_html(session, entry.link)
        image_url = extract_main_image(html)
        abstract = extract_abstract(html)

        # Store in Redis
        item = {
            "title": entry.get("title", "Untitled"),
            "url": entry.get("link", ""),
            "abstract": abstract,
            "category": cat,
            "image": image_url or "",
            "published_ts": time.time(),
        }

        await r.hset(f"rss:item:{uid}", mapping=item)
        await r.zadd("rss:index", {uid: time.time()})
        await r.xadd("rss:queue", {"uid": uid, "title": item["title"], "image": item["image"]})
        await r.sadd("rss:seen", uid)

        print(f"📰 Stored {uid[:8]} from {cat} ({'🖼️' if image_url else '❌ no image'})")


async def ingest_all_feeds(feeds_conf):
    """Fetch and store all feeds defined in feeds.json."""
    feeds = feeds_conf.get("feeds", {})
    workflow = feeds_conf.get("workflow", {})
    max_per_feed = workflow.get("max_per_feed", 5)

    r = redis.Redis(host="system-redis", port=6379, decode_responses=True)

    print("\n📡 Starting feed ingestion...")
    async with aiohttp.ClientSession() as session:
        tasks = []
        for cat, feed_list in feeds.items():
            for feed_entry in feed_list:
                url = feed_entry.get("url")
                if url:
                    tasks.append(process_feed(r, session, cat, url, max_per_feed))
        await asyncio.gather(*tasks)
    print("✅ Feed ingestion complete.\n")