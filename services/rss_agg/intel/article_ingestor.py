#!/usr/bin/env python3
import asyncio
import time
import json
import aiohttp
from bs4 import BeautifulSoup
import redis.asyncio as redis
from datetime import datetime

# ---------- Logging helper ----------
def log(component, status, emoji, msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{component}] [{status}] {emoji} {msg}")


# ---------- Extract full article HTML ----------
async def fetch_html(session, url):
    try:
        async with session.get(url, timeout=15) as r:
            if r.status == 200:
                return await r.text()
    except Exception as e:
        log("article", "error", "⚠️", f"HTML fetch failed for {url}: {e}")
    return ""


# ---------- Minimal extraction with BeautifulSoup ----------
def extract_content(html):
    soup = BeautifulSoup(html, "html.parser")

    # Paragraph text
    paragraphs = [
        p.get_text().strip()
        for p in soup.find_all("p")
        if len(p.get_text().strip()) > 40
    ]

    abstract = paragraphs[0] if paragraphs else ""
    full_text = "\n\n".join(paragraphs)

    # First meaningful image
    img = soup.find("img")
    image_url = img["src"] if img and img.get("src") else ""

    return abstract, full_text, image_url


# ---------- Main enrichment loop ----------
async def enrich_articles(interval_sec=90):
    """
    Reads rss:item:* from intel-redis
    Fetches full content
    Pushes enriched articles to vexy:intake
    """

    intel = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)
    log("article", "ok", "🚀", f"Article enrichment loop started (interval={interval_sec}s)")

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # Get newest items first
                uids = await intel.zrevrange("rss:index", 0, 50)
                if not uids:
                    log("article", "info", "💤", "No items found in rss:index")
                    await asyncio.sleep(interval_sec)
                    continue

                log("article", "info", "🔎", f"Scanning {len(uids)} items for enrichment")

                for uid in uids:
                    key = f"rss:item:{uid}"
                    item = await intel.hgetall(key)
                    if not item:
                        continue

                    url = item.get("url", "")
                    if not url:
                        continue

                    # Skip if already enriched
                    if item.get("enriched") == "1":
                        continue

                    log("article", "info", "📰", f"Enriching article {uid[:8]} → {url}")

                    # Fetch HTML
                    html = await fetch_html(session, url)
                    if not html:
                        continue

                    abstract, full_text, image_url = extract_content(html)

                    # Update Redis article with enriched fields
                    await intel.hset(key, mapping={
                        "abstract": abstract,
                        "full_text": full_text,
                        "image": image_url,
                        "enriched": "1",
                        "enriched_ts": time.time(),
                    })

                    # Push enriched payload to vexy:intake
                    payload = {
                        "uid": uid,
                        "title": item.get("title", ""),
                        "url": url,
                        "abstract": abstract,
                        "image": image_url,
                        "text": full_text[:2000],  # cap for safety
                        "timestamp": time.time(),
                    }

                    await intel.xadd("vexy:intake", payload)
                    log("article", "ok", "📤", f"Pushed enriched article {uid[:8]} → vexy:intake")

                # sleep after finishing loop
                log("article", "info", "⏳", f"Sleeping {interval_sec}s")
                await asyncio.sleep(interval_sec)

            except Exception as e:
                log("article", "error", "🔥", f"Unhandled error in article enrichment: {e}")
                await asyncio.sleep(interval_sec)