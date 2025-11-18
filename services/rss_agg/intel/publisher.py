import os
import time
import redis
from xml.sax.saxutils import escape

r_intel = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)


# ------------------------------------------------------------
# Extract title safely
# ------------------------------------------------------------
def build_title(article: dict) -> str:
    """
    Priority:
      1. canonical 'title' if present
      2. canonical 'abstract' first sentence
      3. fallback to 'Untitled'
    """

    title = (article.get("title") or "").strip()
    if title:
        return escape(title)

    # fallback: use first sentence of abstract
    abstract = (article.get("abstract") or "").strip()
    if abstract:
        s = abstract.split(".")
        return escape(s[0].strip() or "Untitled")

    return "Untitled"


# ------------------------------------------------------------
# Extract a “safe” description
# ------------------------------------------------------------
def build_description(article: dict) -> str:
    """
    Description priority:
      1. abstract
      2. first 2–3 sentences of clean_text
    """
    abstract = (article.get("abstract") or "").strip()
    if abstract:
        return escape(abstract)

    text = (article.get("clean_text") or "").strip()
    if not text:
        return ""

    # sentence extraction that handles newline and whitespace noise
    raw_sentences = text.replace("\n", " ").split(".")
    sentences = [s.strip() for s in raw_sentences if s.strip()]

    lead = ". ".join(sentences[:3])
    if lead:
        return escape(lead)

    return ""


# ------------------------------------------------------------
# Build pubDate
# ------------------------------------------------------------
def build_pubdate(article: dict) -> str:
    """
    Uses fetched_ts stored in canonical record.
    This is the *closest available approximation* to actual pub date
    (Google Alerts usually surface items within ~1 hour).
    """
    ts = float(article.get("fetched_ts", time.time()))
    return time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(ts))


# ------------------------------------------------------------
# Pick the best image
# ------------------------------------------------------------
def build_image(article: dict) -> str:
    """
    Priority:
      1. article['image'] if stored
      2. look for image in enrichment (if present later)
      3. return ""
    """
    if article.get("image"):
        return article["image"]

    # future: enriched image metadata
    if article.get("enriched_image"):
        return article["enriched_image"]

    return ""


# ------------------------------------------------------------
# Builds <item> blocks for RSS XML
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
    Only publish_dir is required.
    Categories come from Redis keys: rss:articles_by_category:*
    """

    if not os.path.exists(publish_dir):
        os.makedirs(publish_dir, exist_ok=True)

    # Find categories dynamically
    keys = r_intel.keys("rss:articles_by_category:*")
    categories = [k.split(":", 2)[2] for k in keys]

    print(f"[publisher] Categories discovered: {categories}")

    for category in categories:
        set_key = f"rss:articles_by_category:{category}"
        uids = r_intel.smembers(set_key)

        if not uids:
            print(f"[publisher] (skip) No articles for {category}")
            continue

        items_xml = ""
        for uid in uids:
            art_key = f"rss:article_canonical:{uid}"
            article = r_intel.hgetall(art_key)
            if not article:
                continue

            items_xml += build_rss_item(article)

        out_path = os.path.join(publish_dir, f"{category}.xml")
        write_rss_feed(category, items_xml, out_path)

        print(f"[publisher] ✔ wrote {out_path}")

    print("[publisher] ✔ All feeds generated")