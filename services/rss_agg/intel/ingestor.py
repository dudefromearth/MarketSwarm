#!/usr/bin/env python3
import asyncio
import aiohttp
import feedparser
import urllib.parse
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
            # MSN usually embeds the full URL already decoded
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

        # If not a wrapper — return as-is
        return url

    except Exception:
        return ""


# ============================================================
# URL VALIDATOR
# ============================================================
def validate_origin(url: str) -> bool:
    """
    Accept ONLY clean HTTP(S) URLs.
    Reject tracking, base64, javascript, mailto, etc.
    """
    if not url or not isinstance(url, str):
        return False

    parsed = urllib.parse.urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return False

    if not parsed.netloc:
        return False

    # Reject google/msn/yahoo wrappers — these must have been unwrapped earlier
    forbidden = ["google.com/url", "msn.com", "news.google.com"]
    if any(f in url for f in forbidden):
        return False

    return True


# ============================================================
# INGESTOR ENTRYPOINT
# ============================================================
async def ingest_feeds(feeds_cfg: dict):
    """
    Feeds.json → category → clean URLs stored into:
      - rss:category_links:{category} (TTL 48h)
      - rss:all_links (no TTL)
    """
    r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)

    feeds = feeds_cfg.get("feeds", {})

    async with aiohttp.ClientSession() as session:

        for category, sources in feeds.items():
            log("link_ingestor", "📡", f"Category: {category}")

            # Redis structures
            cat_key = f"rss:category_links:{category}"

            total_found = 0
            total_saved = 0
            total_rejected = 0

            # Each category contains an array of RSS URLs
            for src in sources:
                feed_url = src.get("url")
                if not feed_url:
                    continue

                log("link_ingestor", "🌐", f"Fetching feed → {feed_url}")

                # -----------------------------------------------------
                # Fetch RSS feed
                # -----------------------------------------------------
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

                    # unwrap Google/MSN/Yahoo
                    clean = unwrap_url(link)

                    if not validate_origin(clean):
                        log("link_ingestor", "⛔", f"Rejected: {link}")
                        total_rejected += 1
                        continue

                    # store in category
                    added = await r.sadd(cat_key, clean)
                    if added:
                        total_saved += 1

                    # global history
                    await r.sadd("rss:all_links", clean)

            # 48-hour rolling TTL
            await r.expire(cat_key, 172800)

            log("link_ingestor", "✅",
                f"{category}: found={total_found} saved={total_saved} rejected={total_rejected}")


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