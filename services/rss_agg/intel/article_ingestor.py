#!/usr/bin/env python3
import asyncio
import time
import json
import redis.asyncio as redis
from datetime import datetime

# Tier-3 LLM enricher
from .tier3_enricher import generate_tier3_metadata

# ------------------------------------------------------------
# Logging helper
# ------------------------------------------------------------
def log(component, status, emoji, msg):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{component}] [{status}] {emoji} {msg}")

# ------------------------------------------------------------
# Tier-3 enrichment loop — Markdown-based only
# ------------------------------------------------------------
async def enrich_articles(interval_sec=90):
    """
    Tier-3 pipeline:
      1. Pulls articles from canonical Tier-0 store ONLY
      2. Reads markdown substrate (no HTML)
      3. Generates metadata with LLM
      4. Stores Tier-3 enriched article
      5. Publishes onto vexy:intake

    No HTML is ever processed here.
    """

    intel = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)

    log("article", "ok", "🚀", f"Tier-3 enrichment loop started (interval={interval_sec}s)")

    while True:
        try:
            # canonical substrate index
            uids = await intel.zrevrange("rss:article_canonical_index", 0, 50)

            if not uids:
                log("article", "info", "💤", "No canonical Tier-0 articles available")
                await asyncio.sleep(interval_sec)
                continue

            log("article", "info", "🔎", f"Scanning {len(uids)} canonical articles")

            for uid in uids:
                canon_key = f"rss:article_canonical:{uid}"
                enriched_key = f"rss:article:{uid}"

                # skip already enriched
                if await intel.exists(enriched_key):
                    continue

                raw = await intel.hgetall(canon_key)
                if not raw:
                    continue

                log("article", "info", "📝", f"Tier-3 enriching {uid[:8]}")

                # canonical fields
                title = raw.get("title", "")
                url = raw.get("url", "")
                category = raw.get("category", "")
                markdown = raw.get("markdown", "")

                if not markdown or len(markdown) < 50:
                    log("article", "warn", "⚠️", f"Canonical markdown too short → {uid[:8]}")
                    continue

                # ------------------------------------------------------------
                # Tier-3 LLM metadata
                # ------------------------------------------------------------
                meta = generate_tier3_metadata(
                    markdown=markdown,
                    title=title,
                    category=category,
                    url=url,
                )

                if not meta:
                    log("article", "error", "🔥", f"Tier-3 LLM failed for {uid[:8]}")
                    continue

                # ------------------------------------------------------------
                # Store enriched Tier-3 article
                # ------------------------------------------------------------
                mapping = {
                    "uid": uid,
                    "url": url,
                    "title": meta["clean_title"],
                    "markdown": meta["markdown"],           # enriched markdown
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
                    "tier": "3",
                    "enriched_ts": time.time(),
                }

                await intel.hset(enriched_key, mapping=mapping)
                await intel.zadd("rss:article_index", {uid: time.time()})

                log("article", "ok", "💎", f"Stored Tier-3 article {uid[:8]}")

                # publish
                await intel.xadd("vexy:intake", mapping)
                log("article", "ok", "📤", f"Pushed Tier-3 article {uid[:8]} → vexy:intake")

            log("article", "info", "⏳", f"Sleeping {interval_sec}s")
            await asyncio.sleep(interval_sec)

        except Exception as e:
            log("article", "error", "🔥", f"Unhandled enrichment error: {e}")
            await asyncio.sleep(interval_sec)