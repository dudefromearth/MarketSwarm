#!/usr/bin/env python3
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
# LLM PROMPT
# ------------------------------------------------------------
TIER3_PROMPT = """
You are an expert financial editor and analyst.

Given the raw article text below, produce a structured JSON object with:

1. "clean_title" – rewrite title in neutral, objective journalistic tone.
2. "abstract" – 2–3 sentence news-style abstract.
3. "summary" – 2–3 paragraph executive summary.
4. "takeaways" – bullet list of 3–6 key points.
5. "sentiment" – "Bullish", "Bearish", or "Neutral".
6. "entities" – list of major people, orgs, macro forces.
7. "tickers" – list of stock tickers if present.
8. "category" – classify into: 
   ["macro", "equities", "fx", "rates", "crypto", "earnings", "energy", "commodities", "politics", "geopolitics", "misc"].
9. "quality_score" – 0.0 to 1.0 (clarity, relevance, originality).
10. "reading_time" – minutes to read (integer estimation).
11. "hero_image" – best guess relevant image URL (fallback to provided).

Return ONLY a JSON object. Do not include commentary.
"""


# ------------------------------------------------------------
# MAIN LLM CALL
# ------------------------------------------------------------
def generate_tier3_metadata(raw_text: str, title: str, fallback_image: str = ""):
    """
    Produces enriched Tier-3 metadata using LLM.
    """
    try:
        content = f"""
TITLE:
{title}

ARTICLE TEXT:
{raw_text}
"""

        response = client.responses.create(
            model="gpt-4.2",
            reasoning={"effort": "medium"},
            input=[
                {"role": "system", "content": TIER3_PROMPT},
                {"role": "user", "content": content}
            ]
        )

        raw_json = response.output_text
        enriched = json.loads(raw_json)

        # Insert fallback hero image if needed
        if fallback_image and not enriched.get("hero_image"):
            enriched["hero_image"] = fallback_image

        enriched["generated_ts"] = time.time()

        return enriched

    except Exception as e:
        log("error", "🔥", f"LLM enrichment failed: {e}")
        return None