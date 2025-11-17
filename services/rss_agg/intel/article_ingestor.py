#!/usr/bin/env python3
import asyncio
import time
import json
import redis.asyncio as redis
from datetime import datetime

import re


# Tier-3 LLM enricher
from .tier3_enricher import generate_tier3_metadata


# ------------------------------------------------------------
# Logging helper
# ------------------------------------------------------------
def log(component, status, emoji, msg):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{component}] [{status}] {emoji} {msg}")


# ------------------------------------------------------------
# FIX 2 — Robust fallback extractor (now applied on canonical text)
# ------------------------------------------------------------
def fallback_extract_text(text: str) -> dict:
    """
    Strong fallback cleaner for canonical text.
    This guarantees downstream text is clean & usable.
    """
    if not text:
        return {"clean_text": "", "abstract": "", "sentences": []}

    # normalize whitespace
    clean = re.sub(r"\s+", " ", text).strip()

    # sentence split
    sentences = [
        s.strip() for s in re.split(r"[.!?]\s+", clean)
        if len(s.strip()) > 20
    ]

    abstract = sentences[0] if sentences else clean[:200]

    return {
        "clean_text": clean,
        "abstract": abstract,
        "sentences": sentences
    }


# ------------------------------------------------------------
# Tier-3 enrichment loop — NOW CANONICAL-BASED
# ------------------------------------------------------------
async def enrich_articles(interval_sec=90):
    """
    NEW Tier-3 pipeline:
      1. Pulls articles from canonical Tier-0 store ONLY
      2. Cleans using FIX-2 text extractor
      3. Generates metadata with LLM
      4. Stores Tier-3 enriched article
      5. Publishes onto vexy:intake

    No HTML is ever processed here.
    """

    intel = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)

    log("article", "ok", "🚀",
        f"Tier-3 enrichment loop started (interval={interval_sec}s)")

    while True:
        try:
            # canonical substrate index
            uids = await intel.zrevrange("rss:article_canonical:index", 0, 50)

            if not uids:
                log("article", "info", "💤",
                    "No canonical Tier-0 articles available")
                await asyncio.sleep(interval_sec)
                continue

            log("article", "info", "🔎",
                f"Scanning {len(uids)} canonical articles")

            for uid in uids:
                canon_key = f"rss:article_canonical:{uid}"
                enriched_key = f"rss:article:{uid}"

                # skip already enriched
                if await intel.exists(enriched_key):
                    continue

                raw = await intel.hgetall(canon_key)
                if not raw:
                    continue

                log("article", "info", "📝",
                    f"Tier-3 enriching {uid[:8]}")

                # canonical fields
                title = raw.get("title", "")
                url = raw.get("url", "")
                category = raw.get("category", "")
                text = raw.get("text", "")

                if not text or len(text) < 50:
                    log("article", "warn", "⚠️",
                        f"Canonical text too short → {uid[:8]}")
                    continue

                # ------------------------------------------------------------
                # FIX-2 fallback extraction (on canonical clean text)
                # ------------------------------------------------------------
                extracted = fallback_extract_text(text)
                clean_text = extracted["clean_text"]
                abstract = extracted["abstract"]
                sentences = extracted["sentences"]

                # ------------------------------------------------------------
                # Tier-3 LLM metadata
                # ------------------------------------------------------------
                meta = generate_tier3_metadata(
                    raw_text=clean_text,
                    title=title,
                    fallback_image=raw.get("main_image", "")
                )

                if not meta:
                    log("article", "error", "🔥",
                        f"Tier-3 LLM failed for {uid[:8]}")
                    continue

                # ------------------------------------------------------------
                # Store enriched Tier-3 article
                # ------------------------------------------------------------
                mapping = {
                    "uid": uid,
                    "url": url,
                    "title": meta["clean_title"],

                    # summary & metadata
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

                    # FIX-2 outputs
                    "full_text": clean_text,
                    "cleaned_text": clean_text,
                    "sentence_0": sentences[0] if len(sentences) > 0 else "",
                    "sentence_1": sentences[1] if len(sentences) > 1 else "",
                    "sentence_2": sentences[2] if len(sentences) > 2 else "",

                    "tier": "3",
                    "enriched_ts": time.time(),
                }

                await intel.hset(enriched_key, mapping=mapping)
                await intel.zadd("rss:article:index", {uid: time.time()})

                log("article", "ok", "💎",
                    f"Stored Tier-3 article {uid[:8]}")

                # publish
                await intel.xadd("vexy:intake", mapping)
                log("article", "ok", "📤",
                    f"Pushed Tier-3 article {uid[:8]} → vexy:intake")

            log("article", "info", "⏳",
                f"Sleeping {interval_sec}s")
            await asyncio.sleep(interval_sec)

        except Exception as e:
            log("article", "error", "🔥",
                f"Unhandled enrichment error: {e}")
            await asyncio.sleep(interval_sec)