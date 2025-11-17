#!/usr/bin/env python3
import asyncio
import redis.asyncio as redis
from datetime import datetime
from .article_fetcher import fetch_and_store_article


def log(comp, status, emoji, msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{comp}] [{status}] {emoji} {msg}")


async def raw_fetch_loop():

    r = redis.Redis(
        host="127.0.0.1",
        port=6381,
        decode_responses=True
    )

    stream = "rss:raw_fetch_queue"
    last_id = "0-0"

    log("raw_fetch", "ok", "🚀", "Continuous raw-fetch loop started")

    while True:
        try:
            msgs = await r.xread({stream: last_id}, block=2000, count=1)
            if not msgs:
                continue

            _, entries = msgs[0]
            last_id, data = entries[0]

            uid = data["uid"]
            url = data["url"]
            title = data.get("title", "")
            category = data.get("category", "")

            await fetch_and_store_article(uid, url, title, category, r)

        except Exception as e:
            log("raw_fetch", "error", "🔥", f"Loop error: {e}")
            await asyncio.sleep(1)