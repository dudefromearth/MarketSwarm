#!/usr/bin/env python3
"""
Canonical Article Schema Builder
--------------------------------
Takes raw HTML → produces deterministic structured article object.

This is the *root substrate* for the entire pipeline.
"""

import re
import time
from dataclasses import dataclass, asdict
from bs4 import BeautifulSoup, Comment
from datetime import datetime


# ------------------------------------------------------------
# Canonical Article Schema (Tier-0 substrate)
# ------------------------------------------------------------
@dataclass
class CanonicalArticle:
    uid: str
    url: str
    title: str
    category: str

    # timestamps
    fetched_ts: float
    normalized_ts: float

    # raw HTML snapshot
    raw_html: str

    # cleaned substrate fields
    text: str           # plain cleaned text
    abstract: str       # first meaningful paragraph
    main_image: str     # first valid image
    word_count: int
    source_domain: str


# ------------------------------------------------------------
# HARD HTML STRIPPER — canonical text extractor
# ------------------------------------------------------------
def extract_clean_text(raw_html: str) -> str:
    """Canonical hard-cleaner: removes *all* HTML constructs."""
    if not raw_html:
        return ""

    # LXML parser = far stricter and cleaner
    soup = BeautifulSoup(raw_html, "lxml")

    # Remove scripts, styles, comments, noscript, meta, svg, etc
    for tag in soup([
        "script", "style", "noscript",
        "meta", "link", "iframe", "svg", "picture",
        "source", "header", "footer", "form"
    ]):
        tag.decompose()

    # Kill HTML comments
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()

    # Get pure text with normalized breaks
    text = soup.get_text(separator="\n")

    # Collapse multiple blank lines
    text = re.sub(r"\n{2,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


# ------------------------------------------------------------
# First meaningful paragraph → abstract
# ------------------------------------------------------------
def extract_abstract(text: str) -> str:
    for para in text.split("\n\n"):
        if len(para.strip()) > 40:
            return para.strip()[:400]
    return ""


# ------------------------------------------------------------
# First real image
# ------------------------------------------------------------
def extract_image(raw_html: str) -> str:
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "lxml")
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src and not src.startswith("data:"):
            return src
    return ""


# ------------------------------------------------------------
# Schema builder — Tier-0 canonicalizer
# ------------------------------------------------------------
def build_canonical_article(raw: dict) -> CanonicalArticle:
    uid = raw.get("uid")
    url = raw.get("url")
    title = raw.get("title", "Untitled")
    category = raw.get("category", "")
    raw_html = raw.get("raw_html", "")
    fetched_ts = float(raw.get("fetched_ts", time.time()))

    # Extract canonical fields
    clean_text = extract_clean_text(raw_html)
    abstract = extract_abstract(clean_text)
    main_image = extract_image(raw_html)

    return CanonicalArticle(
        uid=uid,
        url=url,
        title=title,
        category=category,
        fetched_ts=fetched_ts,
        normalized_ts=time.time(),
        raw_html=raw_html,
        text=clean_text,
        abstract=abstract,
        main_image=main_image,
        word_count=len(clean_text.split()),
        source_domain=url.split("/")[2] if "://" in url else "",
    )


# ------------------------------------------------------------
# Export helper
# ------------------------------------------------------------
def as_mapping(article: CanonicalArticle) -> dict:
    """Convert article dataclass → dict suitable for Redis storage."""
    return asdict(article)