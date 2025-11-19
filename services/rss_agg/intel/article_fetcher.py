#!/usr/bin/env python3
"""
Step-3 Article Enrichment (Markdown Baseline, LIFO)
---------------------------------------------------
Input:  rss:article_canonical:<uid>   (markdown, abstract, image, metadata)
Output: rss:article_enriched:<uid>
        rss:article_enriched_index
        rss:enrich:processed_set
        rss:enrich:stats:*

LLM receives canonical MARKDOWN as the raw_text.
"""

import asyncio
import time
import json
import redis.asyncio as redis
from datetime import datetime

from .tier3_enricher import generate_tier3_metadata

# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------
def log(comp, emoji, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{comp}] {emoji} {msg}")


# ------------------------------------------------------------
# MAIN ENRICHMENT LOOP — Markdown-first
# ------------------------------------------------------------
async def enrich_articles_lifo(interval_sec=30):

    r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)

    log("enrich", "🚀", f"LIFO Tier-3 enrichment (interval={interval_sec}s)")

    while True:
        start_cycle = time.time()

        try:
            # ------------------------------------------------------------
            # Pull newest canonical articles (markdown-first)
            # ------------------------------------------------------------
            uids = await r.zrevrange("rss:article_canonical_index", 0, 200)

            if not uids:
                log("enrich", "💤", "No canonical articles available")
                await asyncio.sleep(interval_sec)
                continue

            for uid in uids:

                enriched_key = f"rss:article_enriched:{uid}"

                # Skip if already enriched
                if await r.exists(enriched_key):
                    continue

                # Skip if already processed
                if await r.sismember("rss:enrich:processed_set", uid):
                    continue

                canon_key = f"rss:article_canonical:{uid}"
                canon = await r.hgetall(canon_key)

                if not canon:
                    continue

                markdown = canon.get("markdown", "")
                if len(markdown) < 100:
                    log("enrich", "⚠️", f"Markdown too short → skip {uid[:8]}")
                    await r.incr("rss:enrich:stats:skipped_short")
                    await r.sadd("rss:enrich:processed_set", uid)
                    continue

                title = canon.get("title", "")
                fallback_image = canon.get("image") or canon.get("main_image") or ""

                # --------------------------------------------------------
                # Run Tier-3 LLM on MARKDOWN
                # --------------------------------------------------------
                log("enrich", "🧠", f"Enriching {uid[:8]}...")
                t0 = time.time()

                meta = generate_tier3_metadata(
                    raw_text=markdown,         # ✔ LLM receives clean markdown
                    title=title,
                    fallback_image=fallback_image
                )

                if not meta:
                    log("enrich", "🔥", f"LLM failed {uid[:8]}")
                    await r.incr("rss:enrich:stats:failed")
                    await r.sadd("rss:enrich:processed_set", uid)
                    continue

                # --------------------------------------------------------
                # Build enriched mapping
                # --------------------------------------------------------
                enriched = {
                    "uid": uid,
                    "url": canon.get("url"),
                    "category": canon.get("category"),
                    "title": meta["clean_title"],

                    # Canonical markdown + metadata
                    "markdown": markdown,
                    "abstract": meta["abstract"],
                    "image": meta["hero_image"],

                    # Deep metadata JSON (flattened)
                    "summary": meta["summary"],
                    "takeaways": json.dumps(meta["takeaways"]),
                    "entities": json.dumps(meta["entities"]),
                    "tickers": json.dumps(meta["tickers"]),
                    "sentiment": meta["sentiment"],
                    "quality_score": meta["quality_score"],
                    "reading_time": meta["reading_time"],

                    # Housekeeping
                    "tier": "enriched",
                    "source_uid": uid,
                    "enriched_ts": time.time(),
                }

                # --------------------------------------------------------
                # Store enriched record
                # --------------------------------------------------------
                await r.hset(enriched_key, mapping=enriched)
                await r.expire(enriched_key, 7 * 86400)  # 7-day TTL

                # Index newest first
                await r.zadd("rss:article_enriched_index", {uid: time.time()})

                # Mark processed
                await r.sadd("rss:enrich:processed_set", uid)
                await r.expire("rss:enrich:processed_set", 7 * 86400)

                await r.incr("rss:enrich:stats:success")

                dt = time.time() - t0
                log("enrich", "✅", f"Enriched {uid[:8]} in {dt:.2f}s")

            cycle_dt = time.time() - start_cycle
            log("enrich", "⏳", f"Cycle complete in {cycle_dt:.2f}s → sleeping {interval_sec}s")
            await asyncio.sleep(interval_sec)

        except Exception as e:
            log("enrich", "🔥", f"Fatal enrichment error: {e}")
            await asyncio.sleep(interval_sec)