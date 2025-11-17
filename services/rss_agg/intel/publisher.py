# publisher.py — Premium Abstract RSS Publisher

import os
import json
from datetime import datetime
from xml.sax.saxutils import escape
import redis

def generate_all_feeds(feeds_conf: dict, truth: dict):
    """
    Generate Premium Abstract RSS feeds from enriched articles in Redis.
    """
    comp = truth["components"]["rss_agg"]
    publish_dir = comp["workflow"]["publish_dir"]
    if not os.path.isabs(publish_dir):
        publish_dir = os.path.abspath(publish_dir)

    r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)

    feeds = feeds_conf.get("feeds", {})
    workflow = feeds_conf.get("workflow", {})
    max_items = int(workflow.get("max_items", 50))

    index_key = comp["access_points"]["index_key"]

    for category in feeds.keys():
        print(f"📝 Generating feed: {category}")

        uids = r.zrevrange(index_key, 0, max_items - 1)

        items = []
        for uid in uids:
            h = r.hgetall(f"rss:item:{uid}")
            if h and h.get("category") == category:
                enriched = r.hgetall(f"rss:article:{uid}")  # enriched article
                items.append(merge_item_and_article(h, enriched))

        xml = render_rss_xml(category, items)

        final_path = os.path.join(publish_dir, f"{category}.xml")
        tmp_path = final_path + ".tmp"

        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(xml)

        os.replace(tmp_path, final_path)
        print(f"   → wrote {final_path} (atomic)")


def merge_item_and_article(item: dict, article: dict):
    """
    Merge raw RSS item + enriched article data into a unified object
    for RSS construction.
    """

    if not article:
        return {
            "uid": item.get("uid"),
            "title": item.get("title"),
            "link": item.get("url"),
            "abstract": item.get("abstract"),
            "image": item.get("image"),
            "pub": item.get("timestamp")
        }

    # Pick best abstract available
    abstract = (
        article.get("summary")
        or article.get("abstract")
        or (article.get("text", "")[:300] + "...")
        or item.get("abstract", "")
    )

    return {
        "uid": item.get("uid"),
        "title": article.get("title") or item.get("title"),
        "link": article.get("canonical_url") or item.get("url"),
        "abstract": abstract,
        "image": article.get("hero_image") or article.get("image") or item.get("image"),
        "pub": article.get("published_ts") or item.get("timestamp")
    }


def render_rss_xml(category: str, items: list):
    now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append('<rss version="2.0">')
    out.append("<channel>")
    out.append(f"<title>{escape(category)}</title>")
    out.append(f"<description>Premium Abstract RSS: {escape(category)}</description>")
    out.append(f"<pubDate>{now}</pubDate>")

    for it in items:
        title = escape(it.get("title", "Untitled"))
        link = escape(it.get("link", ""))
        desc = escape(it.get("abstract", ""))
        pubDate = escape(str(it.get("pub", now)))

        out.append("<item>")
        out.append(f"<title>{title}</title>")
        if link:
            out.append(f"<link>{link}</link>")
        out.append(f"<pubDate>{pubDate}</pubDate>")
        out.append(f"<description>{desc}</description>")

        if it.get("image"):
            out.append(f"<enclosure url=\"{escape(it['image'])}\" type=\"image/jpeg\" />")

        out.append("</item>")

    out.append("</channel>")
    out.append("</rss>")

    return "\n".join(out)