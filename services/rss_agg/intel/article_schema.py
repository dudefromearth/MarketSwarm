#!/usr/bin/env python3
"""
Canonical Article Schema Builder — Markdown Baseline
---------------------------------------------------
This Tier-0 canonicalizer is now markdown-first.

It takes raw HTML → Readability → Markdown + metadata → CanonicalArticle
"""

import re
import time
from dataclasses import dataclass, asdict
from bs4 import BeautifulSoup
from readability import Document
from markdownify import markdownify as html_to_md


# ------------------------------------------------------------
# Canonical Article Schema (Tier-0, Markdown-first)
# ------------------------------------------------------------
@dataclass
class CanonicalArticle:
    uid: str
    url: str
    title: str
    category: str

    fetched_ts: float
    normalized_ts: float

    # snapshots
    raw_html: str
    markdown: str

    # metadata
    abstract: str
    main_image: str
    word_count: int
    source_domain: str


# ------------------------------------------------------------
# HTML → Readability → Markdown
# ------------------------------------------------------------
def extract_markdown(raw_html: str) -> tuple[str, str, str]:
    """
    Returns: (markdown, abstract, first_image)
    """

    if not raw_html:
        return "", "", ""

    # 1) Readability isolate main content
    try:
        doc = Document(raw_html)
        main_html = doc.summary(html_partial=True)
    except Exception:
        main_html = raw_html

    # 2) Convert to Markdown
    markdown = html_to_md(main_html, strip=True)

    # 3) Parse main HTML for metadata
    soup = BeautifulSoup(main_html, "html.parser")

    # Extract first usable image
    first_img = ""
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src and not src.startswith("data:"):
            first_img = src
            break

    # 4) Compute abstract (first meaningful paragraph)
    plain = soup.get_text(separator="\n")
    plain = re.sub(r"\n\s*\n", "\n\n", plain)
    plain = re.sub(r"[ \t]+", " ", plain).strip()

    abstract = ""
    for p in plain.split("\n\n"):
        if len(p.strip()) > 40:
            abstract = p.strip()
            break

    if not abstract and markdown:
        # fallback: first 300 chars of markdown
        abstract = markdown[:300]

    return markdown.strip(), abstract.strip(), first_img


# ------------------------------------------------------------
# Title extractor (matches canonical_fetcher hierarchy)
# ------------------------------------------------------------
def extract_title(raw_html: str, fallback: str = "") -> str:
    if not raw_html:
        return fallback or "Untitled"

    soup = BeautifulSoup(raw_html, "html.parser")

    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()

    if soup.title and soup.title.string:
        return soup.title.string.strip()

    h1 = soup.find("h1")
    if h1 and h1.get_text():
        return h1.get_text().strip()

    return fallback or "Untitled"


# ------------------------------------------------------------
# Core schema builder
# ------------------------------------------------------------
def build_canonical_article(raw: dict) -> CanonicalArticle:
    uid = raw.get("uid")
    url = raw.get("url")
    category = raw.get("category", "")
    raw_html = raw.get("raw_html", "")
    fetched_ts = float(raw.get("fetched_ts", time.time()))

    # markdown + metadata
    markdown, abstract, main_image = extract_markdown(raw_html)

    # Extract title AFTER readability so fallback is better
    title = extract_title(raw_html, fallback=raw.get("title", ""))

    return CanonicalArticle(
        uid=uid,
        url=url,
        title=title or "Untitled",
        category=category,

        fetched_ts=fetched_ts,
        normalized_ts=time.time(),

        raw_html=raw_html,
        markdown=markdown,

        abstract=abstract,
        main_image=main_image,
        word_count=len(markdown.split()),
        source_domain=url.split("/")[2] if "://" in url else "",
    )


# ------------------------------------------------------------
# Export helper — dict for Redis
# ------------------------------------------------------------
def as_mapping(article: CanonicalArticle) -> dict:
    return asdict(article)