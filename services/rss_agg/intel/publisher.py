#!/usr/bin/env python3
"""
publisher.py
------------
Tier-4 + Tier-5D Premium RSS Feed Publisher

Pipeline:
  - Tier 3 articles (LLM-enriched)
  - Tier 0 canonical articles (fallback)
  - Tier 4 premium overlays (context blocks)
  - Tier 5D market-anomaly feed (tail events)

Outputs:
  category.xml
  tail_events.xml
"""

import os
import json
import time
from datetime import datetime
from xml.sax.saxutils import escape

import redis
from openai import OpenAI

# Tail-event subsystem
from .tail_detector import generate_tail_events_feed


# ============================================================
# OpenAI Client
# ============================================================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def ai(prompt: str) -> str:
    """LLM wrapper with safe defaults."""
    r = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        temperature=0.3,
    )
    return r.choices[0].message.content.strip()


# ============================================================
# PUBLIC ENTRYPOINT — Generate All Feeds
# ============================================================
def generate_all_feeds(feeds_conf: dict, truth: dict):
    comp = truth["components"]["rss_agg"]

    publish_dir = comp["workflow"]["publish_dir"]
    if not os.path.isabs(publish_dir):
        publish_dir = os.path.abspath(publish_dir)

    os.makedirs(publish_dir, exist_ok=True)

    r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)

    feeds = feeds_conf["feeds"]
    max_items = int(feeds_conf["workflow"].get("max_items", 50))

    index_key = comp["access_points"]["index_key"]

    # --------------------------------------------------------
    # Generate each category feed
    # --------------------------------------------------------
    for category in feeds.keys():

        print(f"📝 Generating Tier-4 feed for category: {category}")

        uids = r.zrevrange(index_key, 0, max_items - 1)
        items = []

        for uid in uids:

            # Tier-3 enriched
            enriched = r.hgetall(f"rss:article:{uid}")
            if enriched and enriched.get("category") == category:
                enriched["_tier"] = "tier3"
                items.append(enriched)
                continue

            # Canonical fallback
            canon = r.hgetall(f"rss:article_canonical:{uid}")
            if canon and canon.get("category") == category:
                canon["_tier"] = "canonical"
                items.append(canon)
                continue

        # No items → still publish a minimal feed
        context_blocks = build_context_blocks(category, items)

        xml = render_feed(category, context_blocks + items)

        final_path = os.path.join(publish_dir, f"{category}.xml")
        tmp_path = final_path + ".tmp"

        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(xml)
        os.replace(tmp_path, final_path)

        print(f"   → wrote {final_path}")

    # --------------------------------------------------------
    # Generate Global Tail-Event Feed (Tier-5D)
    # --------------------------------------------------------
    print("⚠️  Generating Global Tail-Event Feed...")
    generate_tail_events_feed(publish_dir)
    print("   → tail_events.xml complete.")


# ============================================================
# STEP 4 — AI Context Blocks
# ============================================================
def build_context_blocks(category: str, items: list):
    """
    Builds 3 synthetic context entries:
      1. Category Overview
      2. Rolling Weekly Meta-Summary
      3. AI Highlights (bullets)
    These appear at the top of the feed.
    """

    summaries = [it.get("summary") for it in items if it.get("summary")]
    titles = [it.get("title") for it in items]

    summaries_joined = "\n".join(summaries[:20])

    # ------------------------------
    # 1. CATEGORY OVERVIEW
    # ------------------------------
    category_blurb = ai(
        f"Explain the category '{category}' to a financial professional. "
        f"Cover: why it matters, relevant signals, macro relevance, and how to interpret this category’s feed."
    )

    # ------------------------------
    # 2. WEEKLY SUMMARY
    # ------------------------------
    weekly = ai(
        f"Summarize the last week of news in category '{category}'. "
        f"Here are the article summaries:\n\n{summaries_joined}\n\n"
        f"Extract themes, regime shifts, and risks."
    )

    # ------------------------------
    # 3. AI HIGHLIGHTS
    # ------------------------------
    highlights = ai(
        "From the following article titles, produce 3–5 high-value bullet point insights:\n\n"
        + "\n".join(titles[:15])
    )

    now = time.time()

    return [
        {
            "_special": True,
            "title": f"{category.upper()} — Category Overview",
            "abstract": category_blurb[:600],
            "content": category_blurb,
            "published_ts": now,
        },
        {
            "_special": True,
            "title": f"{category.upper()} — Weekly Meta Summary",
            "abstract": weekly[:600],
            "content": weekly,
            "published_ts": now,
        },
        {
            "_special": True,
            "title": f"{category.upper()} — AI Highlights",
            "abstract": highlights[:600],
            "content": highlights,
            "published_ts": now,
        },
    ]


# ============================================================
# RSS Renderer — Tier-4 Renderer
# ============================================================
def render_feed(category: str, items: list):

    now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append(
        '<rss version="2.0" '
        'xmlns:media="http://search.yahoo.com/mrss/" '
        'xmlns:content="http://purl.org/rss/1.0/modules/content/">'
    )
    out.append("<channel>")
    out.append(f"<title>{escape(category)}</title>")
    out.append(f"<description>Tier-4 Premium Feed: {escape(category)}</description>")
    out.append(f"<pubDate>{now}</pubDate>")

    for it in items:

        title = escape(it.get("title", "Untitled"))
        link = escape(it.get("url", ""))

        ts = float(it.get("published_ts", time.time()))
        pubdate = datetime.utcfromtimestamp(ts).strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )

        abstract = escape((it.get("abstract") or "")[:600])
        content = it.get("content") or it.get("summary") or it.get("abstract") or ""

        out.append("<item>")
        out.append(f"<title>{title}</title>")
        if link:
            out.append(f"<link>{link}</link>")
        out.append(f"<pubDate>{pubdate}</pubDate>")
        out.append(f"<description>{abstract}</description>")
        out.append(f"<content:encoded><![CDATA[{content}]]></content:encoded>")
        out.append("</item>")

    out.append("</channel>")
    out.append("</rss>")

    return "\n".join(out)