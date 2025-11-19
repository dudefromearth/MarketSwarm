#!/usr/bin/env python3
"""
Step-3 Article Enrichment (LIFO, Synchronous + Fallback)
--------------------------------------------------------
Input:  rss:article_canonical:<uid>
Output: rss:article_enriched:<uid>
"""

import time
import json
import os
import redis
from datetime import datetime

from .tier3_enricher import generate_tier3_metadata


# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------
def log(comp, emoji, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{comp}] {emoji} {msg}")


# ------------------------------------------------------------
# ENV FLAGS
# ------------------------------------------------------------
LLM_MODE = os.getenv("LLM_MODE", "online").lower()   # online | offline
# future: we can add LLM_HEALTHCHECK here if needed


# ------------------------------------------------------------
# Deterministic Fallback (Mode C)
# ------------------------------------------------------------
def fallback_metadata(uid, title, clean_text, image):
    """
    LLM-shaped deterministic fallback.
    Ensures enrichment ALWAYS produces a complete object.
    """

    # 1) Abstract = first paragraph or first 300 chars
    parts = clean_text.split("\n")
    abstract = ""
    for p in parts:
        if len(p.strip()) > 40:
            abstract = p.strip()
            break
    if not abstract:
        abstract = clean_text[:300].strip()

    # 2) Summary = 2 short paragraphs made from text
    paragraphs = clean_text.split("\n\n")
    summary = "\n\n".join(paragraphs[:2]).strip()
    if not summary:
        summary = clean_text[:400]

    # 3) Entities (super simple guess)
    entities = []
    for word in clean_text.split():
        if word.istitle() and len(word) > 3:
            entities.append(word)
        if len(entities) >= 10:
            break

    # 4) Tickers (simple $SYMBOL detector)
    tickers = []
    for token in clean_text.split():
        if token.startswith("$") and len(token) <= 6:
            tickers.append(token[1:].upper())

    # 5) Sentiment (simple heuristic)
    sentiment = "Neutral"
    lower = clean_text.lower()
    if any(w in lower for w in ["surge", "gain", "strong"]):
        sentiment = "Bullish"
    if any(w in lower for w in ["fall", "weak", "concern"]):
        sentiment = "Bearish"

    # 6) Reading time
    word_count = len(clean_text.split())
    reading_time = max(1, word_count // 200)

    return {
        "clean_title": title or "Untitled",
        "abstract": abstract,
        "summary": summary,
        "takeaways": [],
        "entities": entities,
        "tickers": tickers,
        "sentiment": sentiment,
        "category": "misc",
        "quality_score": 0.20,
        "reading_time": reading_time,
        "hero_image": image,
        "generated_ts": time.time(),
    }


# ------------------------------------------------------------
# Try LLM → else fallback
# ------------------------------------------------------------
def try_llm_or_fallback(title, clean_text, image, uid):
    """
    Preferred LLM → If error → fallback. Always returns a valid metadata dict.
    """

    # Operator explicitly disabled LLM
    if LLM_MODE == "offline":
        log("enrich", "🚫", f"LLM_MODE=offline → fallback for {uid[:8]}")
        return fallback_metadata(uid, title, clean_text, image)

    # Try the LLM, but catch everything
    try:
        meta = generate_tier3_metadata(
            raw_text=clean_text,
            title=title,
            fallback_image=image
        )
        if not meta:
            raise ValueError("LLM returned None")

        return meta

    except Exception as e:
        log("enrich", "⚠️", f"LLM error → fallback for {uid[:8]} ({e})")
        return fallback_metadata(uid, title, clean_text, image)


# ------------------------------------------------------------
# Main Enrichment — Synchronous
# ------------------------------------------------------------
def enrich_articles_lifo():
    """
    Enrich newest-first (LIFO).
    Never reprocess. Never fail. Always fallback safely.
    """

    r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)

    log("enrich", "🚀", "Starting synchronous LIFO enrichment")

    # Pull newest canonical UIDs
    uids = r.zrevrange("rss:article_canonical_index", 0, 200)
    if not uids:
        log("enrich", "💤", "No canonical articles found")
        return

    for uid in uids:
        enriched_key = f"rss:article_enriched:{uid}"

        # Already enriched?
        if r.exists(enriched_key):
            continue

        # Already processed?
        if r.sismember("rss:enrich:processed_set", uid):
            continue

        canon_key = f"rss:article_canonical:{uid}"
        canon = r.hgetall(canon_key)
        if not canon:
            continue

        clean_text = canon.get("markdown", "") or canon.get("clean_text", "")
        title = canon.get("title", "")
        image = canon.get("image", "")

        if not clean_text or len(clean_text) < 100:
            log("enrich", "⚠️", f"Too short → skip {uid[:8]}")
            r.incr("rss:enrich:stats:skipped_short")
            r.sadd("rss:enrich:processed_set", uid)
            continue

        log("enrich", "🧠", f"Processing {uid[:8]}")

        # --- LLM or fallback ---
        meta = try_llm_or_fallback(title, clean_text, image, uid)

        # --- Build enriched record ---
        enriched = {
            "uid": uid,
            "url": canon.get("url"),
            "category": canon.get("category"),
            "title": meta["clean_title"],
            "abstract": meta["abstract"],
            "summary": meta["summary"],
            "image": meta["hero_image"],
            "clean_text": clean_text,

            "takeaways": json.dumps(meta["takeaways"]),
            "entities": json.dumps(meta["entities"]),
            "tickers": json.dumps(meta["tickers"]),
            "sentiment": meta["sentiment"],
            "quality_score": meta["quality_score"],
            "reading_time": meta["reading_time"],

            "tier": "enriched",
            "source_uid": uid,
            "enriched_ts": time.time(),
        }

        # Store enriched
        r.hset(enriched_key, mapping=enriched)
        r.expire(enriched_key, 604800)

        # Index
        r.zadd("rss:article_enriched_index", {uid: time.time()})

        # Mark processed
        r.sadd("rss:enrich:processed_set", uid)
        r.expire("rss:enrich:processed_set", 604800)

        r.incr("rss:enrich:stats:success")
        log("enrich", "✅", f"Enriched {uid[:8]}")

    log("enrich", "🏁", "Enrichment cycle complete")