#!/usr/bin/env python3
import asyncio
import time
import redis.asyncio as redis
from datetime import datetime
from bs4 import BeautifulSoup


def log(comp, status, emoji, msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{comp}] [{status}] {emoji} {msg}")


def extract_from_raw(html):
    soup = BeautifulSoup(html, "html.parser")

    paragraphs = [
        p.get_text().strip()
        for p in soup.find_all("p")
        if len(p.get_text().strip()) > 40
    ]

    abstract = paragraphs[0] if paragraphs else ""
    full_text = "\n\n".join(paragraphs)

    img = soup.find("img")
    image_url = img["src"] if img and img.get("src") else ""

    return abstract, full_text, image_url


async def enrich_articles():

    r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)

    log("article", "ok", "📝", "Enrichment loop…")

    raw_ids = await r.zrevrange("rss:article_raw:index", 0, 200)

    for uid in raw_ids:
        enriched_key = f"rss:article:{uid}"
        raw_key = f"rss:article_raw:{uid}"

        if await r.exists(enriched_key):
            continue

        raw = await r.hgetall(raw_key)
        if not raw:
            continue

        html = raw.get("raw_html", "")
        if not html:
            continue

        abstract, full_text, image_url = extract_from_raw(html)

        await r.hset(enriched_key, mapping={
            "uid": uid,
            "url": raw["url"],
            "title": raw["title"],
            "category": raw["category"],
            "abstract": abstract,
            "full_text": full_text,
            "cleaned_text": full_text,
            "image": image_url,
            "published_ts": raw.get("timestamp", time.time()),
            "enriched_ts": time.time(),
            "enriched": "1"
        })

        await r.xadd("vexy:intake", {
            "uid": uid,
            "title": raw["title"],
            "category": raw["category"],
            "abstract": abstract,
            "image": image_url,
            "text": full_text[:2000],
            "url": raw["url"],
            "timestamp": time.time(),
        })

        log("article", "ok", "✨", f"Enriched {uid[:8]}")