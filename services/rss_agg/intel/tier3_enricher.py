#!/usr/bin/env python3
"""
Tier-3 Enricher (Markdown Baseline)
-----------------------------------
Input:
    - raw_text: canonical MARKDOWN (not HTML, not plain text)
    - title: canonical extracted title
    - fallback_image: canonical first-img

Output:
    - JSON metadata block used by article_enricher.py
    - All fields required by the Tier-3 enriched schema
"""

import os
import time
import json
from datetime import datetime
from openai import OpenAI

# ------------------------------------------------------------
# LLM Client
# ------------------------------------------------------------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ------------------------------------------------------------
# Logging helper
# ------------------------------------------------------------
def log(status, emoji, msg):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [tier3] [{status}] {emoji} {msg}")

# ------------------------------------------------------------
# Prompt (Markdown-aware)
# ------------------------------------------------------------
TIER3_PROMPT = """
You are an expert financial editor, analyst, and summarizer.

You will receive:
- an article TITLE
- the full article content in MARKDOWN format (clean, human-readable)
- optional fallback image URL

Your job is to output a **pure JSON object** with the following keys:

1. "clean_title"  
   • Rewrite title in neutral, journalistic tone.

2. "abstract"  
   • A tight 2–3 sentence market-news abstract.

3. "summary"  
   • A 2–3 paragraph executive summary.

4. "takeaways"  
   • List of 3–6 concise bullet-point key insights.

5. "sentiment"  
   • One of: "Bullish", "Bearish", "Neutral".

6. "entities"  
   • JSON list of key people, companies, macro forces, or geopolitical actors.

7. "tickers"  
   • JSON list of any stock tickers detected.

8. "category"  
   • One of:
     ["macro", "equities", "fx", "rates", "crypto",
      "earnings", "energy", "commodities",
      "politics", "geopolitics", "misc"]

9. "quality_score"  
   • Float 0.0–1.0 measuring clarity, relevance, coherence.

10. "reading_time"  
    • Estimated minutes to read (integer).

11. "hero_image"  
    • Best-guess relevant image URL.
      If not certain, leave empty; the system will provide a fallback.

Return **ONLY a JSON object**. No commentary.
"""

# ------------------------------------------------------------
# ENV Flag for LLM usage
LLM_MODE = os.getenv("LLM_MODE", "online").lower()  # "online" or "offline"

# ------------------------------------------------------------
# Fallback metadata function
def fallback_metadata(raw_text: str, title: str, fallback_image: str = "") -> dict:
    # Estimate abstract
    parts = raw_text.split("\n\n")
    abstract = ""
    for p in parts:
        if len(p.strip()) > 40:
            abstract = p.strip()
            break
    if not abstract:
        abstract = raw_text[:300].strip()

    # Estimate summary (first two paragraphs)
    summary = "\n\n".join(parts[:2]).strip()
    if not summary:
        summary = raw_text[:400].strip()

    # Reading time (words / 200)
    word_count = len(raw_text.split())
    reading_time = max(1, word_count // 200)

    # Hero image fallback
    hero_image = fallback_image or ""

    # Deterministic fallback fields
    return {
        "clean_title": title or "Untitled",
        "abstract": abstract,
        "summary": summary,
        "takeaways": [],
        "entities": [],
        "tickers": [],
        "sentiment": "Neutral",
        "category": "misc",
        "quality_score": 0.20,
        "reading_time": reading_time,
        "hero_image": hero_image,
        "generated_ts": time.time(),
    }

# ------------------------------------------------------------
# MAIN CALL
def generate_tier3_metadata(raw_text: str, title: str, fallback_image: str = "") -> dict:
    """
    Runs Tier-3 enrichment using canonical MARKDOWN as the input text.
    If LLM_MODE is offline or call fails, returns fallback metadata.
    """

    if LLM_MODE == "offline":
        log("info", "🚫", "LLM_MODE=offline → using fallback metadata")
        return fallback_metadata(raw_text, title, fallback_image)

    try:
        content = f"""
TITLE:
{title}

MARKDOWN ARTICLE CONTENT:
{raw_text}

FALLBACK IMAGE:
{fallback_image}
""".strip()

        response = client.responses.create(
            model="gpt-4.2",
            reasoning={"effort": "medium"},
            input=[
                {"role": "system", "content": TIER3_PROMPT},
                {"role": "user", "content": content}
            ]
        )

        raw_json = response.output_text.strip()
        enriched = json.loads(raw_json)

        # If hero_image missing, fallback
        if fallback_image and not enriched.get("hero_image"):
            enriched["hero_image"] = fallback_image

        enriched["generated_ts"] = time.time()
        return enriched

    except Exception as e:
        log("error", "🔥", f"LLM enrichment failed: {e}")
        return fallback_metadata(raw_text, title, fallback_image)