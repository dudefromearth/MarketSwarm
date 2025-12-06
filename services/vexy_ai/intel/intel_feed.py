#!/usr/bin/env python3
"""
intel_feed.py — Consume rss_agg intel (vexy:intake on intel-redis)
and publish actionable play-by-play commentary to market-redis.
"""

import json
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import redis

from .publisher import publish


INTEL_STREAM_KEY = os.getenv("INTEL_STREAM_KEY", "vexy:intake")
INTEL_STREAM_BATCH = int(os.getenv("INTEL_STREAM_BATCH", "20"))
STATE_KEY = os.getenv("INTEL_STATE_KEY", "vexy_ai:intel:last_id")


def _redis_from_url(url: str) -> redis.Redis:
    parsed = urlparse(url or "redis://127.0.0.1:6381")
    return redis.Redis(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 6381,
        decode_responses=True,
    )


def _parse_json_field(val: Optional[str]) -> Any:
    if not val:
        return None
    try:
        return json.loads(val)
    except Exception:
        return None


def _build_commentary(article: Dict[str, Any]) -> str:
    title = article.get("title") or "Untitled"
    summary = article.get("summary") or article.get("abstract") or ""
    takeaways = article.get("takeaways") or []
    if isinstance(takeaways, str):
        parsed = _parse_json_field(takeaways)
        if parsed:
            takeaways = parsed
    if not isinstance(takeaways, list):
        takeaways = []

    parts = [f"{title} — {summary}".strip()]

    # Add up to two concise takeaways if available
    trimmed = [t.strip() for t in takeaways if isinstance(t, str) and t.strip()]
    if trimmed:
        parts.append("Key takeaways: " + "; ".join(trimmed[:2]))

    return " ".join([p for p in parts if p])


def _build_meta(article: Dict[str, Any]) -> Dict[str, Any]:
    tickers = article.get("tickers")
    if isinstance(tickers, str):
        tickers = _parse_json_field(tickers)
    if not isinstance(tickers, list):
        tickers = []

    return {
        "source": "rss",
        "uid": article.get("uid"),
        "url": article.get("url"),
        "category": article.get("category"),
        "tickers": tickers,
        "sentiment": article.get("sentiment"),
        "importance": article.get("quality_score"),
        "kind": "intel_article",
    }


def process_intel_articles(r_system: redis.Redis, emit) -> int:
    """
    Read new articles from intel-redis stream (vexy:intake), turn them
    into actionable play-by-play commentary, and publish to market-redis.

    Returns number of published messages.
    """
    intel_url = os.getenv("INTEL_REDIS_URL", "redis://127.0.0.1:6381")
    r_intel = _redis_from_url(intel_url)

    last_id = r_system.get(STATE_KEY) or "0-0"

    try:
        msgs = r_intel.xread(
            {INTEL_STREAM_KEY: last_id},
            count=INTEL_STREAM_BATCH,
            block=1000,
        )
    except Exception as e:
        emit("intel", "fail", f"Failed to read {INTEL_STREAM_KEY}: {e}")
        return 0

    if not msgs:
        return 0

    # xread returns list like [(stream, [(id, fields), ...])]
    _, entries = msgs[0]

    published = 0
    latest_id = last_id

    for msg_id, fields in entries:
        latest_id = msg_id
        # rss_agg publishes either plain fields or {"item": json}
        if "item" in fields:
            article = _parse_json_field(fields.get("item")) or {}
        else:
            article = dict(fields)

        commentary = _build_commentary(article)
        meta = _build_meta(article)

        if not commentary:
            continue

        publish("event", commentary, meta)
        published += 1

    # persist last processed id to avoid duplicates across restarts
    try:
        r_system.set(STATE_KEY, latest_id)
    except Exception:
        pass

    return published
