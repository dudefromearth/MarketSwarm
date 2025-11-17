#!/usr/bin/env python3
import asyncio
import time
import json
import redis.asyncio as redis
from datetime import datetime

from bs4 import BeautifulSoup

# NEW: Tier-3 LLM enricher
from .tier3_enricher import generate_tier3_metadata


# ------------------------------------------------------------
# Logging helper
# ------------------------------------------------------------
def log(component, status, emoji, msg):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{component}] [{status}] {emoji} {msg}")


# ------------------------------------------------------------
# Extract readable text from raw HTML
# ------------------------------------------------------------
def extract_readable_text(raw_html: str):
    soup = BeautifulSoup(raw_html, "html.parser")
    paragraphs = [
        p.get_text().strip()
        for p in soup.find_all("p")
        if len(p.get_text().strip()) > 40
    ]
    return "\n\n".join(paragraphs)


# ------------------------------------------------------------
# Main Tier-3 enrichment loop
# ------------------------------------------------------------
async def enrich_articles(interval_sec=90):
    """
    Tier-3 enrichment pipeline:
      1. Find raw articles in rss:article_raw:{uid}
      2. Extract readable text
      3. LLM: summarization, metadata, rewriting
      4. Store into rss:article:{uid}
      5. Publish to vexy:intake
    """
    intel = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)

    log("article", "ok", "🚀", f"Tier-3 enrichment loop started (interval={interval_sec}s)")

    while True:
        try:
            # Pull most recent raw articles
            raw_uids = await intel.zrevrange("rss:article_raw:index", 0, 50)

            if not raw_uids:
                log("article", "info", "💤", "No raw articles available")
                await asyncio.sleep(interval_sec)
                continue

            log("article", "info", "🔎", f"Scanning {len(raw_uids)} raw articles")

            for uid in raw_uids:
                raw_key = f"rss:article_raw:{uid}"
                enriched_key = f"rss:article:{uid}"

                # Skip if enriched already exists
                if await intel.exists(enriched_key):
                    continue

                raw = await intel.hgetall(raw_key)
                if not raw:
                    continue

                log("article", "info", "📝", f"Tier-3 enriching {uid[:8]}")

                title = raw.get("title", "")
                url = raw.get("url", "")
                category = raw.get("category", "")

                raw_html = raw.get("raw_html", "")
                if not raw_html:
                    log("article", "warn", "⚠️", f"No raw_html for {uid[:8]}")
                    continue

                # Extract readable text
                clean_text = extract_readable_text(raw_html)

                if len(clean_text) < 80:
                    log("article", "warn", "⚠️",
                        f"Extracted text too short for LLM → {uid[:8]}")
                    continue

                # ------------------------------------------------------------
                # Tier-3 LLM metadata generation
                # ------------------------------------------------------------
                meta = generate_tier3_metadata(
                    raw_text=clean_text,
                    title=title,
                    fallback_image=raw.get("image", "")
                )

                if not meta:
                    log("article", "error", "🔥",
                        f"Tier-3 LLM failed for {uid[:8]}")
                    continue

                # ------------------------------------------------------------
                # Store enriched article
                # ------------------------------------------------------------
                mapping = {
                    "uid": uid,
                    "url": url,
                    "title": meta["clean_title"],
                    "abstract": meta["abstract"],
                    "summary": meta["summary"],
                    "takeaways": json.dumps(meta["takeaways"]),
                    "entities": json.dumps(meta["entities"]),
                    "tickers": json.dumps(meta["tickers"]),
                    "sentiment": meta["sentiment"],
                    "category": meta["category"],
                    "quality_score": meta["quality_score"],
                    "reading_time": meta["reading_time"],
                    "image": meta["hero_image"],
                    "full_text": clean_text,
                    "tier": "3",
                    "enriched_ts": time.time(),
                }

                await intel.hset(enriched_key, mapping=mapping)
                await intel.zadd("rss:article:index", {uid: time.time()})

                log("article", "ok", "💎",
                    f"Stored Tier-3 article {uid[:8]} → rss:article")

                # ------------------------------------------------------------
                # Push to vexy:intake
                # ------------------------------------------------------------
                await intel.xadd("vexy:intake", mapping)
                log("article", "ok", "📤",
                    f"Pushed Tier-3 article {uid[:8]} → vexy:intake")

            log("article", "info", "⏳",
                f"Sleeping {interval_sec}s")
            await asyncio.sleep(interval_sec)

        except Exception as e:
            log("article", "error", "🔥", f"Unhandled enrichment error: {e}")
            await asyncio.sleep(interval_sec)