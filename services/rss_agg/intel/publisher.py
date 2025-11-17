#!/usr/bin/env python3
import os
import json
import time
from datetime import datetime
from xml.sax.saxutils import escape

import redis


# --------------------------------------------------------------------
# Bloomberg-grade RSS publisher
# --------------------------------------------------------------------
def generate_all_feeds(feeds_conf: dict, truth: dict):
    comp = truth["components"]["rss_agg"]

    publish_dir = comp["workflow"]["publish_dir"]
    if not os.path.isabs(publish_dir):
        publish_dir = os.path.abspath(publish_dir)

    r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)

    feeds = feeds_conf.get("feeds", {})
    workflow = feeds_conf.get("workflow", {})
    max_items = int(workflow.get("max_items", 50))

    index_key = comp["access_points"]["index_key"]

    # ----------------------------------------------------------------
    # For each category → generate premium-grade RSS feed
    # ----------------------------------------------------------------
    for category in feeds.keys():
        print(f"📝 Generating Bloomberg-grade feed: {category}")

        uids = r.zrevrange(index_key, 0, max_items - 1)
        items = []

        for uid in uids:

            enriched = r.hgetall(f"rss:article:{uid}")
            if enriched and enriched.get("category") == category:
                items.append(enriched)
                continue

            raw = r.hgetall(f"rss:item:{uid}")
            if raw and raw.get("category") == category:
                items.append(raw)

        xml = render_bloomberg_rss(category, items)

        final_path = os.path.join(publish_dir, f"{category}.xml")
        tmp_path = final_path + ".tmp"

        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(xml)

        os.replace(tmp_path, final_path)
        print(f"   → wrote {final_path} (atomic)")


# --------------------------------------------------------------------
# Bloomberg-grade rendering
# --------------------------------------------------------------------
def render_bloomberg_rss(category: str, items: list):
    now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

    # Add namespaces for advanced RSS
    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append(
        '<rss version="2.0" '
        'xmlns:media="http://search.yahoo.com/mrss/" '
        'xmlns:content="http://purl.org/rss/1.0/modules/content/">'
    )
    out.append("<channel>")
    out.append(f"<title>{escape(category)}</title>")
    out.append(f"<description>Premium feed: {escape(category)}</description>")
    out.append(f"<pubDate>{now}</pubDate>")

    # ------------------------------------------------------------
    # Render each item with Bloomberg-level structure
    # ------------------------------------------------------------
    for it in items:

        title = escape(it.get("title", "Untitled"))
        link = escape(it.get("url", ""))

        ts = (
            float(it.get("published_ts"))
            if it.get("published_ts")
            else float(it.get("timestamp", time.time()))
        )
        pubdate = datetime.utcfromtimestamp(ts).strftime("%a, %d %b %Y %H:%M:%S GMT")

        abstract = it.get("abstract") or it.get("cleaned_text") or ""
        abstract = escape(abstract[:600])

        hero = it.get("image") or ""
        summary = it.get("summary", "")
        reading_time = it.get("reading_time", "")
        sentiment = it.get("sentiment", "")
        tickers = json.loads(it.get("tickers", "[]")) if "tickers" in it else []
        entities = json.loads(it.get("entities", "[]")) if "entities" in it else []
        takeaways = json.loads(it.get("takeaways", "[]")) if "takeaways" in it else []

        # Build HTML content block
        html = []
        html.append("<div style='font-family: Georgia, serif; font-size: 15px;'>")

        # Hero image
        if hero:
            html.append(
                f"<p><img src='{escape(hero)}' style='max-width:100%; border-radius:8px;' /></p>"
            )

        # Summary block
        if summary:
            html.append(f"<p><strong>{escape(summary)}</strong></p>")

        # Bullet takeaways
        if takeaways:
            html.append("<ul>")
            for t in takeaways:
                html.append(f"<li>{escape(t)}</li>")
            html.append("</ul>")

        # Metadata footer
        meta_html = "<p style='color:#666; font-size: 13px;'>"
        if sentiment:
            meta_html += f"Sentiment: <b>{escape(sentiment)}</b> &nbsp; "
        if reading_time:
            meta_html += f"Reading time: {escape(str(reading_time))} min &nbsp; "
        if tickers:
            meta_html += "Tickers: " + ", ".join(tickers) + " &nbsp; "
        if entities:
            meta_html += "Entities: " + ", ".join(entities)
        meta_html += "</p>"

        html.append(meta_html)

        html.append("</div>")
        content_encoded = escape("\n".join(html))

        # --------------------------------------------------------
        # Write RSS <item>
        # --------------------------------------------------------
        out.append("<item>")
        out.append(f"<title>{title}</title>")
        if link:
            out.append(f"<link>{link}</link>")
        out.append(f"<pubDate>{pubdate}</pubDate>")
        out.append(f"<description>{abstract}</description>")

        # Media enclosure
        if hero:
            out.append(
                f'<media:content url="{escape(hero)}" medium="image" type="image/jpeg" />'
            )

        # Full HTML content
        out.append(f"<content:encoded><![CDATA[{content_encoded}]]></content:encoded>")

        out.append("</item>")

    out.append("</channel>")
    out.append("</rss>")

    return "\n".join(out)