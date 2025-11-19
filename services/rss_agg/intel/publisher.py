#!/usr/bin/env python3
"""
publisher.py — Transaction-Safe RSS Publisher with 3-Day Ledger
---------------------------------------------------------------
Writes RSS feeds only when NEW canonical articles exist since
the last successful publish transaction.

Ledger key:
    rss:publish_ledger:{category}  (ZSET, score = published_ts)

TTL:
    Ledger entries auto-expire after 3 days
"""

import os
import time
import redis
from xml.sax.saxutils import escape
import re

# 3-day TTL for ledger entries
PUBLISH_LEDGER_TTL = 3 * 24 * 3600   # 259,200 seconds

r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def build_title(article: dict) -> str:
    title = (article.get("title") or "").strip()
    if title:
        return escape(title)

    abstract = (article.get("abstract") or "").strip()
    if abstract:
        s = abstract.split(".")
        return escape(s[0].strip() or "Untitled")

    return "Untitled"


def build_description(article: dict) -> str:
    # 1 — Prefer explicit abstract
    abstract = (article.get("abstract") or "").strip()
    if abstract:
        return escape(abstract)

    # 2 — fallback to markdown content
    md = (article.get("markdown") or "").strip()
    if not md:
        return ""

    # Normalize whitespace
    text = re.sub(r"\s+", " ", md)

    # Naive sentence detection
    raw_sentences = re.split(r'[.!?]\s+', text)
    sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 0]

    if not sentences:
        return escape(text[:300])

    lead = ". ".join(sentences[:3])
    return escape(lead)


def build_pubdate(article: dict) -> str:
    ts = float(article.get("fetched_ts", time.time()))
    return time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(ts))


def build_image(article: dict) -> str:
    if article.get("image"):
        return article["image"]
    if article.get("hero_image"):
        return article["hero_image"]
    return ""


# ------------------------------------------------------------
# RSS Item Builder
# ------------------------------------------------------------
def build_rss_item(article: dict) -> str:
    title = build_title(article)
    link = escape(article.get("url", ""))
    guid = article.get("uid", "")
    pubDate = build_pubdate(article)
    description = build_description(article)
    image = build_image(article)

    enclosure = ""
    if image:
        enclosure = f'<enclosure url="{escape(image)}" type="image/jpeg" />'

    return f"""
        <item>
            <title>{title}</title>
            <link>{link}</link>
            <guid isPermaLink="false">{guid}</guid>
            <pubDate>{pubDate}</pubDate>
            <description>{description}</description>
            {enclosure}
        </item>
    """


# ------------------------------------------------------------
# Write RSS File
# ------------------------------------------------------------
def write_rss_feed(category: str, items_xml: str, output_path: str):
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
    <title>{escape(category)}</title>
    <description>Automated economic/market intelligence feed for {escape(category)}</description>
    <link>https://marketswarm.ai/feeds/{escape(category)}.xml</link>

    {items_xml}

</channel>
</rss>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml)


# ------------------------------------------------------------
# Ledger Logic
# ------------------------------------------------------------
def get_newest_article_ts(category):
    """
    Read canonical articles for this category and return
    the *newest* fetched timestamp.
    """
    set_key = f"rss:articles_by_category:{category}"
    uids = r.smembers(set_key)

    newest_ts = 0
    for uid in uids:
        art_key = f"rss:article_canonical:{uid}"
        art = r.hgetall(art_key)
        if not art:
            continue
        ts = float(art.get("fetched_ts", 0))
        if ts > newest_ts:
            newest_ts = ts

    return newest_ts


def get_last_publish_ts(category):
    """
    Look inside ledger:
        rss:publish_ledger:{category}

    Return timestamp of most recent publish transaction.
    """
    ledger_key = f"rss:publish_ledger:{category}"
    res = r.zrevrange(ledger_key, 0, 0, withscores=True)
    if not res:
        return 0
    _, ts = res[0]
    return ts


def record_publish_transaction(category, ts):
    """
    Write a ledger event: { published_ts → 1 }
    """
    ledger_key = f"rss:publish_ledger:{category}"
    r.zadd(ledger_key, {1: ts})
    r.expire(ledger_key, PUBLISH_LEDGER_TTL)


# ------------------------------------------------------------
# Publisher Main
# ------------------------------------------------------------
def generate_all_feeds(publish_dir: str):
    if not os.path.exists(publish_dir):
        os.makedirs(publish_dir, exist_ok=True)

    keys = r.keys("rss:articles_by_category:*")
    categories = [k.split(":", 2)[2] for k in keys]

    print(f"[publisher] Categories discovered: {categories}")

    for category in categories:
        set_key = f"rss:articles_by_category:{category}"
        uids = r.smembers(set_key)

        if not uids:
            print(f"[publisher] (skip) No articles for {category}")
            continue

        # ---- Ledger decision ----
        newest_article_ts = get_newest_article_ts(category)
        last_publish_ts = get_last_publish_ts(category)

        if newest_article_ts <= last_publish_ts:
            print(f"[publisher] (skip) No new articles since last publish for {category}")
            continue

        # ---- Build RSS XML ----
        items_xml = ""
        for uid in uids:
            art_key = f"rss:article_canonical:{uid}"
            article = r.hgetall(art_key)
            if not article:
                continue
            items_xml += build_rss_item(article)

        # ---- Write file ----
        out_path = os.path.join(publish_dir, f"{category}.xml")
        write_rss_feed(category, items_xml, out_path)
        print(f"[publisher] ✔ wrote {out_path}")

        # ---- Record transaction ----
        record_publish_transaction(category, time.time())

    print("[publisher] ✔ All feeds generated")