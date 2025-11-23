#!/usr/bin/env python3
from flask import Flask, render_template, jsonify, Response
import redis
import json

app = Flask(__name__, template_folder="admin/templates", static_folder="admin/static")
r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

def event_stream():
    pubsub = r.pubsub()
    pubsub.subscribe("admin:refresh")
    for message in pubsub.listen():
        if message["type"] == "message":
            yield f"data: {message['data']}\n\n"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def status():
    switches = {
        "ingest":     bool(int(r.get("pipeline:switch:ingest") or "1")),
        "canonical":  bool(int(r.get("pipeline:switch:canonical") or "1")),
        "enrich":     bool(int(r.get("pipeline:switch:enrich") or "1")),
        "publish":    bool(int(r.get("pipeline:switch:publish") or "1")),
        "stats":      bool(int(r.get("pipeline:switch:stats") or "1")),
    }
    return jsonify(switches)

@app.route("/api/toggle/<stage>/<int:value>")
def toggle(stage, value):
    key = f"pipeline:switch:{stage}"
    r.set(key, value)
    r.publish("admin:refresh", json.dumps({"action": "switches"}))
    return jsonify({"status": "ok"})

@app.route("/api/articles")
def articles():
    result = []
    print("[admin] Scanning for enriched articles...")

    # Nuclear: find EVERYTHING that might be an enriched article
    patterns = [
        "rss:article_enriched:*",
        "rss:article:*",
        "article_enriched:*",
        "enriched:*",
        "*enriched*"
    ]

    all_keys = set()
    for pattern in patterns:
        found = r.keys(pattern)
        print(f"[admin] Pattern '{pattern}' found {len(found)} keys")
        all_keys.update(found)

    print(f"[admin] Total unique keys to check: {len(all_keys)}")

    for key in all_keys:
        print(f"[admin] Checking key: {key}")
        try:
            data = r.hgetall(key)
            if not data:
                continue

            uid = key.split(":")[-1]

            # Look for any sign of markdown in canonical
            canon_key = f"rss:article_canonical:{uid}"
            canon = r.hgetall(canon_key) if r.exists(canon_key) else {}
            markdown = canon.get("markdown", "") or canon.get("clean_text", "")

            result.append({
                "uid": uid[:8],
                "full_uid": uid,
                "key": key,
                "title": data.get("title") or data.get("clean_title") or data.get("headline") or "Untitled",
                "source": data.get("enrichment_source", "unknown"),
                "model": data.get("enrichment_model", "unknown"),
                "ts": data.get("enriched_at") or data.get("enriched_ts") or data.get("published_at") or "unknown",
                "has_markdown": bool(markdown),
                "markdown_preview": markdown[:150].replace("\n", " ") + "..." if markdown else "No markdown"
            })
        except Exception as e:
            print(f"[admin] Error reading {key}: {e}")

    print(f"[admin] Final result count: {len(result)}")
    return jsonify(result)

@app.route("/api/article/<uid>")
def article(uid):
    # Try every possible key pattern
    possible_keys = [
        f"rss:article_enriched:{uid}",
        f"rss:article:{uid}",
        f"article_enriched:{uid}",
        f"enriched:{uid}"
    ]
    data = {}
    for key in possible_keys:
        if r.exists(key):
            data = r.hgetall(key)
            break
    if not data:
        return "Not found", 404

    canon = r.hgetall(f"rss:article_canonical:{uid}")
    data["markdown"] = canon.get("markdown", "") or canon.get("clean_text", "")
    return jsonify(data)

@app.route("/stream")
def stream():
    return Response(event_stream(), mimetype="text/event-stream")

if __name__ == "__main__":
    print("MarketSwarm Admin UI → http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=True)