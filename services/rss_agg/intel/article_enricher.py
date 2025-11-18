#!/usr/bin/env python3
"""
Step-3 Article Enrichment (LIFO)
--------------------------------
Input:  rss:article_canonical:<uid>
Output: rss:article_enriched:<uid>
        rss:article_enriched_index (ZSET, ts)
        rss:enrich:processed_set (7-day)
        rss:enrich:stats:* counters

This step produces:
  - Flat fields for redis search/feed
  - Deep metadata JSON
  - LLM-enhanced summary, entities, sentiment, title normalization
  - Quality score (LLM)
"""

import asyncio
import time
import json
import redis.asyncio as redis
from datetime import datetime

from .tier3_enricher import generate_tier3_metadata   # You already have this
                                                      # (But not required)

# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------
def log(comp, emoji, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{comp}] {emoji} {msg}")


# ------------------------------------------------------------
# Main Enrichment Loop (NEW)
# ------------------------------------------------------------
async def enrich_articles_lifo(interval_sec=30):
    """
    Enrich canonical articles newest-first.
    Never reprocess the same UID twice.
    Build a flat + deep schema.
    Set 7-day TTL.
    """

    r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)

    log("enrich", "🚀", f"LIFO Tier-3 enrichment (interval={interval_sec}s)")

    while True:
        start_cycle = time.time()

        try:
            # ------------------------------------------------------------
            # Discover canonical articles newest→oldest (LIFO)
            # ------------------------------------------------------------
            uids = await r.zrevrange("rss:article_canonical_index", 0, 200)

            if not uids:
                log("enrich", "💤", "No canonical articles available")
                await asyncio.sleep(interval_sec)
                continue

            for uid in uids:
                enriched_key = f"rss:article_enriched:{uid}"

                # --------------------------------------------------------
                # Idempotency: skip if enriched already
                # --------------------------------------------------------
                if await r.exists(enriched_key):
                    continue

                # Also skip if in processed-set
                if await r.sismember("rss:enrich:processed_set", uid):
                    continue

                canon_key = f"rss:article_canonical:{uid}"
                canon = await r.hgetall(canon_key)

                if not canon:
                    continue

                clean_text = canon.get("clean_text", "")
                if len(clean_text) < 200:
                    log("enrich", "⚠️", f"Too short → skip {uid[:8]}")
                    await r.incr("rss:enrich:stats:skipped_short")
                    # Mark as processed so we don't revisit
                    await r.sadd("rss:enrich:processed_set", uid)
                    continue

                # --------------------------------------------------------
                # Run Tier-3 LLM metadata
                # --------------------------------------------------------
                log("enrich", "🧠", f"Enriching {uid[:8]}...")
                t0 = time.time()

                meta = generate_tier3_metadata(
                    raw_text=clean_text,
                    title=canon.get("title", ""),
                    fallback_image=canon.get("image", "")
                )

                if not meta:
                    log("enrich", "🔥", f"LLM failed {uid[:8]}")
                    await r.incr("rss:enrich:stats:failed")
                    # Mark processed so we don't loop forever
                    await r.sadd("rss:enrich:processed_set", uid)
                    continue

                # --------------------------------------------------------
                # Build enriched mapping (flat fields)
                # --------------------------------------------------------
                enriched = {
                    "uid": uid,
                    "url": canon.get("url"),
                    "category": canon.get("category"),

                    # Canonical fields
                    "abstract": meta["abstract"],
                    "image": meta["hero_image"],
                    "clean_text": clean_text,
                    "title": meta["clean_title"],

                    # Deep metadata (stringified JSON)
                    "summary": meta["summary"],
                    "takeaways": json.dumps(meta["takeaways"]),
                    "entities": json.dumps(meta["entities"]),
                    "sentiment": meta["sentiment"],
                    "tickers": json.dumps(meta["tickers"]),
                    "quality_score": meta["quality_score"],  # YOUR CHOSEN MODEL
                    "reading_time": meta["reading_time"],

                    # Bookkeeping
                    "tier": "enriched",
                    "source_uid": uid,
                    "enriched_ts": time.time(),
                }

                # --------------------------------------------------------
                # Store enriched article
                # --------------------------------------------------------
                await r.hset(enriched_key, mapping=enriched)
                await r.expire(enriched_key, 604800)      # 7 days

                # Index by time
                await r.zadd("rss:article_enriched_index", {uid: time.time()})

                # Mark processed
                await r.sadd("rss:enrich:processed_set", uid)
                await r.expire("rss:enrich:processed_set", 604800)

                await r.incr("rss:enrich:stats:success")

                dt = time.time() - t0
                log("enrich", "✅", f"Enriched {uid[:8]} in {dt:.2f}s")

            cycle_dt = time.time() - start_cycle
            log("enrich", "⏳", f"Cycle complete in {cycle_dt:.2f}s → sleeping {interval_sec}s")
            await asyncio.sleep(interval_sec)

        except Exception as e:
            log("enrich", "🔥", f"Fatal enrichment error: {e}")
            await asyncio.sleep(interval_sec)