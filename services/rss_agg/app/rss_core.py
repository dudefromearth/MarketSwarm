# services/rss_agg/app/rss_core.py
import json
import aiohttp
from redis.asyncio import Redis
from .aggregator import fetch_feed_async, normalize_entry, enrich_article_async, load_feeds_from_schema

async def poll_feeds_once(r: Redis, max_items: int = 5):
    feeds = load_feeds_from_schema()
    total = 0
    async with aiohttp.ClientSession() as session:
        for feed in feeds:
            try:
                fp = await fetch_feed_async(feed, 10, "MarketSwarm/1.0")
                for e in fp.entries[:max_items]:
                    d = normalize_entry(feed, e)
                    enriched = await enrich_article_async(d['url'], d['summary'], session)
                    d['abstract'] = enriched['abstract']
                    d['images'] = json.dumps(enriched['images'])
                    d['extracts'] = json.dumps(enriched['extracts'])
                    await r.hset(f"rss:item:{d['uid']}", mapping=d)
                    await r.zadd("rss:index", {d["uid"]: float(d["published_ts"])})
                    await r.xadd("rss:queue", {"uid": d["uid"], "abstract": d["abstract"]})
                    total += 1
            except Exception as e:
                print(f"[rss_core] ⚠️ Feed error {feed}: {e}")
    return total