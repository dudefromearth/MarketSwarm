#!/usr/bin/env python3
"""
Hybrid Tier-4 Tail Event Detector
---------------------------------
Reads enriched Tier-3 articles, applies hybrid macro-narrative-systemic
analysis, produces a dedicated tail-event RSS feed.

Voice: Institutional Macro × Narrative Intelligence × Strategic Brief × Bloomberg
"""

import os
import time
import json
from datetime import datetime
from xml.sax.saxutils import escape

import redis
from openai import OpenAI


# ------------------------------------------------------------
# OpenAI client
# ------------------------------------------------------------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def ai(prompt: str, max_tokens=450):
    """Helper wrapper."""
    r = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.2
    )
    return r.choices[0].message.content.strip()


# ------------------------------------------------------------
# Tail Scoring Model (Hybrid A+B+C+D)
# ------------------------------------------------------------
def compute_tail_risk_score(article: dict) -> dict:
    """
    Returns:
        {
            "score": 0-100,
            "reason": "...",
            "impacts": {
                "short_term": "...",
                "medium_term": "...",
                "strategic": "..."
            },
            "convexity": [...]   # opportunities
            "sectors": [...]
            "risks": [...]
        }
    """

    title = article.get("title", "")
    summary = article.get("summary", "")
    abstract = article.get("abstract", "")
    full_text = article.get("full_text", "")

    prompt = f"""
You are a hybrid financial intelligence system (macro desk + narrative analyst + risk research + Bloomberg).
Analyze the following article and evaluate whether it contains a *tail event* or regime-shift signal.

ARTICLE TITLE:
{title}

SUMMARY:
{summary}

ABSTRACT:
{abstract}

FULL TEXT:
{full_text[:5000]}

Return JSON ONLY with fields:
{{
  "score": <0-100>,
  "reason": "<1 paragraph, hybrid macro+narrative explanation>",
  "impacts": {{
     "short_term": "<market reaction 1-3 days>",
     "medium_term": "<1-4 weeks impact>",
     "strategic": "<3-12 month implications>"
  }},
  "sectors": ["sector1", ...],
  "risks": ["risk1", ...],
  "convexity": ["optional convex plays"],
  "story_arcs": ["key narrative arcs affecting positioning"],
  "sentiment_shift": "<does the article mark a narrative reversal? yes/no>"
}}
"""

    try:
        result = ai(prompt, max_tokens=600)
        return json.loads(result)
    except Exception as e:
        return {
            "score": 0,
            "reason": f"LLM parsing failed: {e}",
            "impacts": {},
            "sectors": [],
            "risks": [],
            "convexity": [],
            "story_arcs": [],
            "sentiment_shift": "no"
        }


# ------------------------------------------------------------
# Pull recent enriched articles, compute tail-events
# ------------------------------------------------------------
def compute_tail_events(r, limit=80, threshold=65):
    """
    Reads last N enriched articles and returns those with tail risk score >= threshold.
    """

    uids = r.zrevrange("rss:article:index", 0, limit - 1)
    events = []

    for uid in uids:
        art = r.hgetall(f"rss:article:{uid}")
        if not art:
            continue

        score_block = compute_tail_risk_score(art)
        score = int(score_block.get("score", 0))

        if score >= threshold:
            events.append({
                "uid": uid,
                "url": art.get("url", ""),
                "title": art.get("title", ""),
                "published_ts": float(art.get("enriched_ts", time.time())),
                "tail": score_block
            })

    return events


# ------------------------------------------------------------
# Render RSS
# ------------------------------------------------------------
def render_tail_feed(events: list):
    now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append('<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">')
    out.append("<channel>")
    out.append("<title>Market Tail-Event Feed</title>")
    out.append("<description>Extreme signals, anomalies, shocks, regime shifts</description>")
    out.append(f"<pubDate>{now}</pubDate>")

    for ev in events:

        title = escape(ev["title"])
        link = escape(ev["url"])
        ts = datetime.utcfromtimestamp(ev["published_ts"]).strftime("%a, %d %b %Y %H:%M:%S GMT")

        t = ev["tail"]
        reason = t.get("reason", "")
        impacts = t.get("impacts", {})
        sectors = t.get("sectors", [])
        risks = t.get("risks", [])
        convexity = t.get("convexity", [])
        arcs = t.get("story_arcs", [])

        # Build premium HTML
        html = []

        html.append(f"<h3>Tail Score: {t.get('score', 0)}</h3>")
        html.append(f"<p><strong>Why it matters:</strong> {reason}</p>")

        html.append("<h4>Market Impacts</h4>")
        html.append("<ul>")
        if "short_term" in impacts:
            html.append(f"<li><b>Short-term:</b> {impacts['short_term']}</li>")
        if "medium_term" in impacts:
            html.append(f"<li><b>Medium-term:</b> {impacts['medium_term']}</li>")
        if "strategic" in impacts:
            html.append(f"<li><b>Strategic:</b> {impacts['strategic']}</li>")
        html.append("</ul>")

        if sectors:
            html.append("<h4>Affected Sectors</h4><ul>")
            for s in sectors:
                html.append(f"<li>{s}</li>")
            html.append("</ul>")

        if risks:
            html.append("<h4>Risks</h4><ul>")
            for rsk in risks:
                html.append(f"<li>{rsk}</li>")
            html.append("</ul>")

        if convexity:
            html.append("<h4>Convexity Opportunities</h4><ul>")
            for cx in convexity:
                html.append(f"<li>{cx}</li>")
            html.append("</ul>")

        if arcs:
            html.append("<h4>Story Arcs</h4><ul>")
            for a in arcs:
                html.append(f"<li>{a}</li>")
            html.append("</ul>")

        content = "\n".join(html)

        out.append("<item>")
        out.append(f"<title>{title}</title>")
        if link:
            out.append(f"<link>{link}</link>")
        out.append(f"<pubDate>{ts}</pubDate>")
        out.append(f"<description><![CDATA[{escape(reason)}]]></description>")
        out.append(f"<content:encoded><![CDATA[{content}]]></content:encoded>")
        out.append("</item>")

    out.append("</channel></rss>")
    return "\n".join(out)


# ------------------------------------------------------------
# PUBLIC ENTRYPOINT FOR PUBLISHER
# ------------------------------------------------------------
def generate_tail_events_feed(publish_dir: str):
    """Called from publisher.py"""

    r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)

    print("⚡ Computing tail-risk events…")
    events = compute_tail_events(r)

    print(f"⚡ Tail events detected: {len(events)}")

    xml = render_tail_feed(events)

    final_path = os.path.join(publish_dir, "tail_events.xml")
    tmp = final_path + ".tmp"

    with open(tmp, "w", encoding="utf-8") as f:
        f.write(xml)

    os.replace(tmp, final_path)

    print(f"⚡ Wrote tail_events.xml → {final_path}")