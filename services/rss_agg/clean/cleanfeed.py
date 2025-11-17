#!/usr/bin/env python3
import aiohttp
import asyncio
import feedparser
import hashlib
from urllib.parse import urlparse, parse_qs, unquote


# --------------------------------------------------------
# URL Unwrapper — removes Google/MSN/Bing/Yahoo redirects
# --------------------------------------------------------
def unwrap_redirect(url: str) -> str:
    if not url:
        return url

    u = url.lower()

    # --- Google News redirect ---
    if "://www.google.com/url" in u:
        try:
            params = parse_qs(urlparse(url).query)
            return unquote(params.get("url", [url])[0])
        except:
            return url

    # --- Google AMP ---
    if "/amp/" in u:
        return url.replace("/amp/", "/")

    # --- MSN/Bing ---
    if "redir.aspx" in u:
        try:
            params = parse_qs(urlparse(url).query)
            return unquote(params.get("url", [url])[0])
        except:
            return url

    # --- Yahoo Redirect ---
    if "r.search.yahoo.com" in u:
        try:
            params = parse_qs(urlparse(url).query)
            return unquote(params.get("p", [url])[0])
        except:
            return url

    return url


# --------------------------------------------------------
# CleanFeedStage: canonicalize any feed into clean entries
# --------------------------------------------------------
async def clean_feed(feed_url: str, max_items=50):
    """
    Fetch a raw feed and return a list of canonical items:
      {
        'uid': sha1(clean_url),
        'title': ...,
        'clean_url': ...,
        'raw_url': ...,
        'published': ...,
        'clean_id': ...,
      }
    """

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(feed_url, timeout=20) as resp:
                xml = await resp.text()
        except Exception as e:
            print(f"[CleanFeed Error] Cannot fetch {feed_url}: {e}")
            return []

    parsed = feedparser.parse(xml)
    cleaned_items = []

    for entry in parsed.entries[:max_items]:

        # Extract raw values
        raw_id = entry.get("id") or entry.get("link") or entry.get("title")
        raw_url = entry.get("link") or ""

        # --------- Clean + Canonicalize links ---------
        clean_id = unwrap_redirect(raw_id)
        clean_url = unwrap_redirect(raw_url)

        # --------- Stable UID ---------
        uid = hashlib.sha1(clean_url.encode()).hexdigest()

        item = {
            "uid": uid,
            "title": entry.get("title", "Untitled"),
            "raw_url": raw_url,
            "clean_url": clean_url,
            "raw_id": raw_id,
            "clean_id": clean_id,
            "published": entry.get("published", ""),
        }

        cleaned_items.append(item)

    return cleaned_items


# --------------------------------------------------------
# Convenience: pretty-print results for debugging
# --------------------------------------------------------
async def debug_cleanfeed(feed_url):
    items = await clean_feed(feed_url)
    print("\n=== CLEANFEED DEBUG ===")
    for it in items:
        print(f"\n• UID:        {it['uid'][:12]}")
        print(f"  TITLE:      {it['title']}")
        print(f"  RAW URL:    {it['raw_url']}")
        print(f"  CLEAN URL:  {it['clean_url']}")
        print(f"  RAW ID:     {it['raw_id']}")
        print(f"  CLEAN ID:   {it['clean_id']}")
    print("\n=======================\n")


if __name__ == "__main__":
    # Simple manual test
    test_url = "https://www.google.com/alerts/feeds/18068156851767145348/12169640906365262022"
    asyncio.run(debug_cleanfeed(test_url))