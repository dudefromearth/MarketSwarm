import os
import time
import redis
from xml.sax.saxutils import escape

r_intel = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)


# ------------------------------------------------------------
# Extracts a “safe” description
# ------------------------------------------------------------
def build_description(article: dict) -> str:
    """
    Description priority:
      1. abstract (if present)
      2. first 2–3 sentences of clean_text
    """
    abstract = article.get("abstract", "").strip()
    if abstract:
        return escape(abstract)

    text = article.get("clean_text", "")
    if not text:
        return ""

    # crude sentence split
    sentences = text.split(".")
    lead = ".".join(sentences[:3]).strip()
    return escape(lead)


# ------------------------------------------------------------
# Builds <item> blocks for RSS XML
# ------------------------------------------------------------
def build_rss_item(article: dict) -> str:
    title = escape(article.get("title", "Untitled"))
    link = article.get("url", "")
    guid = article.get("uid", "")
    pub_ts = float(article.get("fetched_ts", time.time()))
    pubDate = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(pub_ts))

    description = build_description(article)
    image = article.get("image", "")

    enclosure = ""
    if image:
        enclosure = f'<enclosure url="{escape(image)}" type="image/jpeg" />'

    return f"""
        <item>
            <title>{title}</title>
            <link>{escape(link)}</link>
            <guid isPermaLink="false">{guid}</guid>
            <pubDate>{pubDate}</pubDate>
            <description>{description}</description>
            {enclosure}
        </item>
    """


# ------------------------------------------------------------
# Writes an RSS XML file for a category
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
# Main Publisher API (new signature)
# ------------------------------------------------------------
def generate_all_feeds(publish_dir: str):
    """
    New API: Only publish_dir is required.
    Feeds.json no longer dictates categories for publishing.
    Redis contains the authoritative category list.
    """

    if not os.path.exists(publish_dir):
        os.makedirs(publish_dir, exist_ok=True)

    # Find categories from Redis
    keys = r_intel.keys("rss:articles_by_category:*")
    categories = [k.split(":", 2)[2] for k in keys]

    print(f"[publisher] Categories discovered: {categories}")

    for category in categories:
        # Fetch UIDs for category
        set_key = f"rss:articles_by_category:{category}"
        uids = r_intel.smembers(set_key)

        if not uids:
            print(f"[publisher] (skip) No articles for {category}")
            continue

        # Build item blocks
        items_xml = ""
        for uid in uids:
            art_key = f"rss:article_canonical:{uid}"
            article = r_intel.hgetall(art_key)
            if not article:
                continue

            items_xml += build_rss_item(article)

        # Write RSS XML file
        out_path = os.path.join(publish_dir, f"{category}.xml")
        write_rss_feed(category, items_xml, out_path)

        print(f"[publisher] ✔ wrote {out_path}")

    print("[publisher] ✔ All feeds generated")