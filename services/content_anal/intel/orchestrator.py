#!/usr/bin/env python3
"""
orchestrator.py — Content Analysis Engine
Adaptive LLM pipeline:
  1) collect recent category items
  2) introspect schema
  3) generate synthetic insights
  4) generate graphics
  5) publish new synthetic content
"""

import os
import json
import time
from datetime import datetime, timezone

from .schema_introspector import infer_schema
from .analysis import llm_analyze
from .graphics.render import generate_chart

MIN_ARTICLES = int(os.getenv("CONTENT_ANAL_MIN_ARTICLES", "5"))
CHECK_INTERVAL = int(os.getenv("CONTENT_ANAL_INTERVAL_SEC", "300"))

# ------------------------------------------------------------
# Fetch articles from intel-redis (vexy:intake format)
# ------------------------------------------------------------
def fetch_recent_articles(r_intel, category):
    messages = r_intel.xrevrange("vexy:intake", "+", "-", count=200)

    articles = []
    for _, fields in messages:
        try:
            obj = json.loads(fields.get("item", "{}"))
        except Exception:
            continue

        if obj.get("category") == category:
            articles.append(obj)

    return articles


# ------------------------------------------------------------
# Produce synthetic article (final stage)
# ------------------------------------------------------------
def publish_synthetic(r_intel, outbox_key, article):
    payload = {"item": json.dumps(article)}
    r_intel.xadd(outbox_key, payload)
    print(f"[content_anal] 📝 synthetic article published → {outbox_key}")


# ------------------------------------------------------------
# Main orchestrator loop
# ------------------------------------------------------------
def run_orchestrator(setup_info):
    SERVICE_ID = setup_info["SERVICE_ID"]
    comp        = setup_info["component"]
    truth       = setup_info["truth"]

    r_intel  = setup_info["r_intel"]

    outbox_key = comp["access_points"]["publish_to"][0]["key"]

    print(f"[content_anal] 🔥 starting orchestrator (interval={CHECK_INTERVAL}s)")

    # You may later load categories dynamically; for now one fixed category:
    ALL_CATEGORIES = ["economy", "markets", "crypto", "tech"]

    while True:
        for category in ALL_CATEGORIES:
            print(f"\n[content_anal] 📂 CATEGORY: {category}")

            # 1) collect items
            articles = fetch_recent_articles(r_intel, category)

            print(f"[content_anal] found {len(articles)} articles in {category}")

            if len(articles) < MIN_ARTICLES:
                print(f"[content_anal] skipping — needs {MIN_ARTICLES}")
                continue

            # 2) infer schema
            schema = infer_schema(articles)
            print(f"[content_anal] inferred schema fields: {list(schema.keys())}")

            # 3) LLM analysis
            insight_text = llm_analyze(category, articles, schema)

            # 4) generate chart(s)
            chart_b64 = generate_chart(category, articles, schema)

            # 5) synthetic article
            synthetic = {
                "uid": f"synthetic-{SERVICE_ID}-{int(time.time())}",
                "category": category,
                "ts": datetime.now(timezone.utc).isoformat(),
                "title": f"{category.title()} — Weekly Intelligence Summary",
                "analysis": insight_text,
                "chart": chart_b64,
                "schema_version": 1,
            }

            publish_synthetic(r_intel, outbox_key, synthetic)

        print(f"\n[content_anal] ⏳ sleeping {CHECK_INTERVAL} sec\n")
        time.sleep(CHECK_INTERVAL)