#!/usr/bin/env python3
import asyncio
import aiohttp
import feedparser
import urllib.parse
import os
import redis.asyncio as redis

# ============================================================
# LOGGING
# ============================================================
def log(component, emoji, msg):
    print(f"[{component}] {emoji} {msg}")


# ============================================================
# GOOGLE/BING/YAHOO LINK UNWRAPPER
# ============================================================
def unwrap_url(url: str) -> str:
    """
    Extracts the true origin URL from Google/MSN/Yahoo RSS wrappers.
    Returns "" if URL cannot be unwrapped or validated.
    """

    if not url:
        return ""

    try:
        parsed = urllib.parse.urlparse(url)

        # --- GOOGLE WRAPPER ----------------------------------
        if "google.com" in parsed.netloc and parsed.path == "/url":
            qs = urllib.parse.parse_qs(parsed.query)
            real = qs.get("url") or qs.get("q")
            if real:
                return real[0]

        # --- MSN / BING WRAPPER ------------------------------
        if "msn.com" in parsed.netloc and "url=" in url:
            qs = urllib.parse.parse_qs(parsed.query)
            real = qs.get("url")
            if real:
                return real[0]

        # --- YAHOO WRAPPER ------------------------------------
        if "yahoo.com" in parsed.netloc and "u=" in parsed.query:
            qs = urllib.parse.parse_qs(parsed.query)
            real = qs.get("u")
            if real:
                return real[0]

        # Not a wrapper
        return url

    except Exception:
        return ""


# ============================================================
# URL VALIDATOR
# ============================================================
def validate_origin(url: str) -> bool:
    """
    Accept ONLY clean HTTP(S) URLs.
    """
    if not url or not isinstance(url, str):
        return False

    parsed = urllib.parse.urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False

    # reject wrapper/redirect patterns
    forbidden = ["google.com/url", "msn.com", "news.google.com"]
    if any(f in url for f in forbidden):
        return False

    return True


# ============================================================
# INGESTOR ENTRYPOINT
# ============================================================
async def ingest_feeds(feeds_cfg: dict):
    """
    Feeds.json → category → URLs stored into:
      - rss:category_links:{category} (TTL 48h)
      - rss:all_links
      - rss:seen (unless FORCE_INGEST=true)
    """
    r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)

    FORCE_INGEST = os.getenv("FORCE_INGEST", "false").lower() == "true"
    if FORCE_INGEST:
        log("link_ingestor", "⚡", "FORCE_INGEST enabled — ignoring seen filter")

    feeds = feeds_cfg.get("feeds", {})

    async with aiohttp.ClientSession() as session:

        for category, sources in feeds.items():
            log("link_ingestor", "📡", f"Category: {category}")

            cat_key = f"rss:category_links:{category}"

            total_found = 0
            total_saved = 0
            total_rejected = 0

            for src in sources:
                feed_url = src.get("url")
                if not feed_url:
                    continue

                log("link_ingestor", "🌐", f"Fetching feed → {feed_url}")

                try:
                    async with session.get(feed_url, timeout=20) as resp:
                        raw = await resp.read()
                except Exception as e:
                    log("link_ingestor", "⚠️", f"Failed to fetch feed: {e}")
                    continue

                parsed = feedparser.parse(raw)

                for entry in parsed.entries:
                    total_found += 1

                    link = entry.get("link")
                    if not link:
                        total_rejected += 1
                        continue

                    clean = unwrap_url(link)
                    if not validate_origin(clean):
                        log("link_ingestor", "⛔", f"Rejected: {link}")
                        total_rejected += 1
                        continue

                    uid = clean

                    # ---------------------------------------------------------
                    # NEWNESS FILTER (disabled when FORCE_INGEST=true)
                    # ---------------------------------------------------------
                    if not FORCE_INGEST:
                        if await r.sismember("rss:seen", uid):
                            continue  # skip because we've already ingested it

                    # ---------------------------------------------------------
                    # ALWAYS store the URL (force mode bypasses "added" result)
                    # ---------------------------------------------------------
                    added = await r.sadd(cat_key, clean)
                    if added:
                        total_saved += 1
                    elif FORCE_INGEST:
                        # In force mode, log duplicates so user sees they exist
                        log("link_ingestor", "↩️", f"Already existed (force): {clean}")

                    # Global tracking
                    await r.sadd("rss:all_links", clean)
                    await r.sadd("rss:seen", uid)

            await r.expire(cat_key, 172800)

            log(
                "link_ingestor",
                "✅",
                f"{category}: found={total_found} saved={total_saved} rejected={total_rejected}"
            )


# ============================================================
# INTERVAL SCHEDULER
# ============================================================
async def schedule_link_ingestor(feeds_cfg: dict, interval: int = 600):
    log("link_ingestor", "🚀", f"Starting Tier-0 link ingestor (every {interval}s)")
    while True:
        try:
            await ingest_feeds(feeds_cfg)
        except Exception as e:
            log("link_ingestor", "🔥", f"Fatal ingestion error: {e}")

        await asyncio.sleep(interval)