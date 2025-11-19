#!/usr/bin/env python3
"""
Stage-2 Canonical Article Fetcher — Markdown Baseline (SYNC, NO PROXY)
-----------------------------------------------------------------------
Input:  rss:category_links:<category>
Output: rss:article_canonical:<uid>     (markdown-first, 7d TTL)
        rss:articles_by_category:<category>
        rss:article_canonical_index
        rss:canonical_tried_urls
"""

import hashlib
import time
import re
import requests
from datetime import datetime

import redis
from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_md
from readability import Document


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def log(comp, emoji, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{comp}] {emoji} {msg}")


def uid_from_url(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------
# HTML → readability → markdown + metadata
# ------------------------------------------------------------
def clean_html_to_markdown(raw_html: str):
    if not raw_html:
        return "", "", "", ""

    extracted_title = ""
    try:
        doc = Document(raw_html)
        main_html = doc.summary(html_partial=True)
        extracted_title = (doc.short_title() or "").strip()
    except Exception:
        main_html = raw_html

    # FIXED: strip must be a list, not a boolean
    markdown = html_to_md(
        main_html,
        strip=["script", "style"]   # <-- safe, correct
    )

    soup = BeautifulSoup(main_html, "html.parser")

    # first image
    first_img = ""
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src and not src.startswith("data:"):
            first_img = src
            break

    # title extraction chain
    title = ""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()

    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()

    if not title:
        h1 = soup.find("h1")
        if h1 and h1.get_text():
            title = h1.get_text().strip()

    if not title and extracted_title:
        title = extracted_title

    # abstract extraction
    plain = soup.get_text(separator="\n")
    plain = re.sub(r"\n\s*\n", "\n\n", plain)
    plain = re.sub(r"[ \t]+", " ", plain).strip()

    abstract = ""
    for p in plain.split("\n\n"):
        if len(p.strip()) > 40:
            abstract = p.strip()
            break

    if not title:
        title = abstract[:120].strip()

    return markdown, abstract, first_img, title

# ------------------------------------------------------------
# Fetch HTML (SYNC, requests)
# ------------------------------------------------------------
def fetch_html(url: str):
    try:
        resp = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent":
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/118 Safari/537.36"
            }
        )
        if resp.status_code >= 400:
            log("canon", "⚠️", f"HTTP {resp.status_code} → {url}")
            return None

        return resp.text

    except Exception as e:
        log("canon", "⚠️", f"Fetch error → {e}")
        return None


# ------------------------------------------------------------
# Canonical Fetcher (SYNC)
# ------------------------------------------------------------
def canonical_fetcher_run_once():
    r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)
    tried_key = "rss:canonical_tried_urls"

    total_urls = 0
    total_new = 0
    total_success = 0
    total_fail_net = 0
    total_fail_parse = 0

    log("canon", "🚀", "canonical_fetcher_run_once() starting")

    keys = r.keys("rss:category_links:*")
    categories = [k.split(":")[-1] for k in keys]

    if not categories:
        log("canon", "💤", "No category link sets")
        return

    for category in categories:
        cat_key = f"rss:category_links:{category}"
        urls = r.smembers(cat_key)

        if not urls:
            continue

        log("canon", "📂", f"{category}: {len(urls)} URLs")

        for url in urls:
            total_urls += 1

            if r.sismember(tried_key, url):
                continue

            uid = uid_from_url(url)
            art_key = f"rss:article_canonical:{uid}"

            if r.exists(art_key):
                r.sadd(tried_key, url)
                r.expire(tried_key, 30 * 86400)
                continue

            total_new += 1
            log("canon", "🌐", f"Fetching → {url}")

            raw_html = fetch_html(url)

            if not raw_html or len(raw_html) < 200:
                total_fail_net += 1
                log("canon", "⚠️", "Bad HTML → skip")
                r.sadd(tried_key, url)
                r.expire(tried_key, 30 * 86400)
                continue

            markdown, abstract, first_img, title = clean_html_to_markdown(raw_html)

            if not markdown or len(markdown) < 80:
                total_fail_parse += 1
                log("canon", "⚠️", "Markdown too short → skip")
                r.sadd(tried_key, url)
                r.expire(tried_key, 30 * 86400)
                continue

            mapping = {
                "uid": uid,
                "url": url,
                "category": category,
                "title": title,
                "markdown": markdown,
                "abstract": (abstract or markdown[:500]).strip(),
                "image": first_img,
                "raw_len": len(raw_html),
                "markdown_len": len(markdown),
                "fetched_ts": time.time(),
            }

            # store canonical
            r.hset(art_key, mapping=mapping)
            r.expire(art_key, 7 * 86400)

            # category index
            cat_index = f"rss:articles_by_category:{category}"
            r.sadd(cat_index, uid)
            r.expire(cat_index, 7 * 86400)

            # global index
            r.zadd("rss:article_canonical_index", {uid: time.time()})

            # mark tried
            r.sadd(tried_key, url)
            r.expire(tried_key, 30 * 86400)

            total_success += 1
            log("canon", "✅", f"Stored canonical → {uid}")

    # stats
    r.hset(
        "rss:canonical_stats:last_run",
        mapping={
            "ts": time.time(),
            "total_urls": total_urls,
            "new": total_new,
            "success": total_success,
            "fail_net": total_fail_net,
            "fail_parse": total_fail_parse,
        },
    )

    log(
        "canon",
        "📊",
        f"Run complete: urls={total_urls}, new={total_new}, "
        f"ok={total_success}, net_fail={total_fail_net}, parse_fail={total_fail_parse}"
    )