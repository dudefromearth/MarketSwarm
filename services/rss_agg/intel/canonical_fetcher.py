#!/usr/bin/env python3
"""
Stage-2 Canonical Article Fetcher
---------------------------------
Input:  rss:category_links:<category>   (clean URLs)
Output: rss:article_canonical:<uid>     (7-day canonical articles)
        rss:articles_by_category:<category>
        rss:article_canonical_index
        rss:canonical_tried_urls        (30-day memory of attempts)
"""

import asyncio
import hashlib
import time
from datetime import datetime
import re

import aiohttp
import redis.asyncio as redis
from bs4 import BeautifulSoup


# --------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------
def log(comp: str, emoji: str, msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{comp}] {emoji} {msg}")


def uid_from_url(url: str) -> str:
    """Stable canonical UID based on SHA1(url)."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------
# HTML → clean text / first-image / abstract
# --------------------------------------------------------------------
def clean_html(raw_html: str):
    if not raw_html:
        return "", "", "", "", 0

    soup = BeautifulSoup(raw_html, "html.parser")

    # Remove garbage
    for t in soup(["script", "style", "noscript"]):
        t.decompose()

    # -------------------------------
    # TITLE EXTRACTION (NEW)
    # -------------------------------
    title = ""

    # Priority: og:title
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()

    # Fallback to <title>
    if not title:
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

    # Fallback to first <h1>
    if not title:
        h1 = soup.find("h1")
        if h1 and h1.get_text():
            title = h1.get_text().strip()

    # Fallback last resort later (using abstract)
    # -------------------------------

    # Extract first usable image
    first_img = ""
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src and not src.startswith("data:"):
            first_img = src
            break

    # Extract text
    text = soup.get_text(separator="\n")
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()

    # Abstract = first meaningful paragraph
    abstract = ""
    for p in text.split("\n\n"):
        if len(p.strip()) > 40:
            abstract = p.strip()
            break

    # Fallback title: abstract
    if not title:
        title = abstract[:120].strip()

    return text, first_img, abstract, title


# --------------------------------------------------------------------
# Download HTML (simple HTTP fetch)
# --------------------------------------------------------------------
async def fetch_html(session: aiohttp.ClientSession, url: str) -> str | None:
    try:
        async with session.get(url, timeout=15) as resp:
            if resp.status >= 400:
                log("canon", "⚠️", f"HTTP {resp.status} → {url}")
                return None
            return await resp.text()
    except Exception as e:
        log("canon", "⚠️", f"Network error for {url}: {e}")
        return None


# --------------------------------------------------------------------
# ONE-SHOT canonical fetcher
#  - No internal while True
#  - Orchestrator/scheduler controls when it runs
# --------------------------------------------------------------------
async def canonical_fetcher_run_once():
    """
    Process all category link sets once.

    For each URL in rss:category_links:<category>:
      - Skip if URL is already in rss:canonical_tried_urls
      - Skip if rss:article_canonical:<uid> already exists
      - Fetch HTML, clean, and store canonical article
      - Mark URL as tried in rss:canonical_tried_urls (30-day TTL)
    """

    r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)
    tried_key = "rss:canonical_tried_urls"

    # Stats for this run
    total_urls = 0
    total_new_candidates = 0
    total_success = 0
    total_fail_network = 0
    total_fail_parse = 0

    log("canon", "🚀", "canonical_fetcher_run_once() starting")

    # Discover categories from link sets
    keys = await r.keys("rss:category_links:*")
    categories = [k.split(":", 2)[-1] for k in keys]  # handle rss:category_links:<cat>

    if not categories:
        log("canon", "💤", "No category link sets found; nothing to do")
        return

    async with aiohttp.ClientSession() as session:
        for category in categories:
            cat_key = f"rss:category_links:{category}"
            urls = await r.smembers(cat_key)
            if not urls:
                continue

            log("canon", "📂", f"Category → {category} ({len(urls)} URLs)")

            for url in urls:
                total_urls += 1

                # Skip if we've tried this URL in the last 30 days
                if await r.sismember(tried_key, url):
                    # comment this out if logs get too noisy
                    # log("canon", "↩️", f"Already tried → {url}")
                    continue

                uid = uid_from_url(url)
                art_key = f"rss:article_canonical:{uid}"

                # If canonical article already exists, just mark URL as tried and move on
                if await r.exists(art_key):
                    await r.sadd(tried_key, url)
                    await r.expire(tried_key, 30 * 24 * 3600)
                    # log("canon", "✅", f"Already canonical → {uid}")
                    continue

                total_new_candidates += 1
                log("canon", "🌐", f"Fetching → {url}")

                raw_html = await fetch_html(session, url)
                if not raw_html or len(raw_html) < 200:
                    log("canon", "⚠️", "Bad HTML → skip")
                    total_fail_network += 1

                    # mark as tried even if bad; we don't want to hammer it
                    await r.sadd(tried_key, url)
                    await r.expire(tried_key, 30 * 24 * 3600)
                    continue

                clean_text, first_img, abstract, title = clean_html(raw_html)

                if not clean_text or len(clean_text) < 80:
                    log("canon", "⚠️", "No readable text → skip")
                    total_fail_parse += 1

                    await r.sadd(tried_key, url)
                    await r.expire(tried_key, 30 * 24 * 3600)
                    continue

                # Build canonical mapping
                mapping = {
                    "uid": uid,
                    "url": url,
                    "category": category,
                    "title": title,
                    "raw_len": len(raw_html),
                    "text_len": len(clean_text),
                    "clean_text": clean_text,
                    "abstract": abstract[:500] if abstract else clean_text[:500],
                    "image": first_img,
                    "fetched_ts": time.time(),
                }

                # Store canonical article (7-day TTL)
                await r.hset(art_key, mapping=mapping)
                await r.expire(art_key, 7 * 24 * 3600)

                # Category index (7-day TTL)
                cat_index_key = f"rss:articles_by_category:{category}"
                await r.sadd(cat_index_key, uid)
                await r.expire(cat_index_key, 7 * 24 * 3600)

                # Global index (no TTL — time-based score)
                await r.zadd("rss:article_canonical_index", {uid: time.time()})

                # Mark URL as tried (30-day TTL)
                await r.sadd(tried_key, url)
                await r.expire(tried_key, 30 * 24 * 3600)

                total_success += 1
                log("canon", "✅", f"Stored canonical → {uid}")

    # Store summary stats for this run (optional, but handy)
    stats_key = "rss:canonical_stats:last_run"
    await r.hset(
        stats_key,
        mapping={
            "ts": time.time(),
            "total_urls": total_urls,
            "new_candidates": total_new_candidates,
            "success": total_success,
            "fail_network": total_fail_network,
            "fail_parse": total_fail_parse,
        },
    )

    log(
        "canon",
        "📊",
        (
            f"Run complete. urls={total_urls} "
            f"new={total_new_candidates} "
            f"ok={total_success} "
            f"net_fail={total_fail_network} "
            f"parse_fail={total_fail_parse}"
        ),
    )


# --------------------------------------------------------------------
# OPTIONAL: legacy loop wrapper (not used by orchestrator)
# --------------------------------------------------------------------
async def canonical_fetcher_loop(interval_sec: int = 300):
    """
    Backward-compatible loop wrapper.
    Orchestrator currently uses schedule_canonical_fetcher(),
    which calls canonical_fetcher_run_once() on its own cadence.
    """
    log("canon", "ℹ️", f"canonical_fetcher_loop starting (interval={interval_sec}s)")
    while True:
        await canonical_fetcher_run_once()
        log("canon", "⏳", f"Sleeping {interval_sec}s")
        await asyncio.sleep(interval_sec)