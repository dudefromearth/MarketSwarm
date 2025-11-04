from __future__ import annotations
import hashlib, json, os, re, time
from typing import Dict, Iterable
from collections import Counter
import feedparser
from redis.asyncio import Redis as AsyncRedis
from bs4 import BeautifulSoup
import aiohttp
import asyncio
import sys
from heartbeat import start_heartbeat

def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return default if v is None or v.strip() == "" else v

def clean_url(u: str) -> str:
    _INVIS = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)
    return (u.translate(_INVIS).strip() if isinstance(u, str) else "")

async def fetch_feed_async(url: str, timeout: float, ua: str) -> feedparser.FeedParserDict:
    url = clean_url(url)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers={"User-Agent": ua}, timeout=timeout) as resp:
            if resp.status == 200:
                content = await resp.text()
                return feedparser.parse(content)
            raise Exception(f"HTTP {resp.status}")

def normalize_entry(feed_url: str, e) -> Dict[str, str]:
    link = clean_url(e.get("link") or "")
    guid = clean_url(e.get("id") or link or "")
    uid = hashlib.sha1(guid.encode()).hexdigest()
    pub = e.get("published_parsed") or e.get("updated_parsed")
    ts = int(time.mktime(pub)) if pub else int(time.time())
    src = feed_url.split("/")[2] if "://" in feed_url else feed_url
    title = (e.get("title") or link or "").strip()
    summary = e.get("summary", "")
    return {"uid": uid, "url": link, "source": src, "title": title, "published_ts": str(ts), "summary": summary}

async def enrich_article_async(link: str, abstract: str, session: aiohttp.ClientSession, max_abstract: int = 800) -> dict:
    if len(abstract) > 400:
        return {'abstract': abstract, 'images': [], 'extracts': {'keywords': [], 'quotes': []}}
    try:
        async with session.get(link, headers={"User-Agent": _env("USER_AGENT", "Aggregator/1.0")}, timeout=10) as resp:
            if resp.status != 200:
                return {'abstract': abstract, 'images': [], 'extracts': {'keywords': [], 'quotes': []}}
            content = await resp.text()
            soup = BeautifulSoup(content, 'html.parser')
            body = soup.find('article') or soup.find('div', class_='story-body') or soup.find('main')
            if body:
                paras = body.find_all('p')[:3]
                full_text = ' '.join(p.get_text(strip=True) for p in paras)
                abstract = full_text[:max_abstract] + '...' if len(full_text) > max_abstract else full_text
            text_lower = (full_text or abstract).lower()
            words = re.findall(r'\b[a-z]{4,}\b', text_lower)
            keywords = [word for word, _ in Counter(words).most_common(5)]
            quotes = [strong.get_text(strip=True) for strong in soup.find_all(['strong', 'b']) if len(strong.get_text()) > 20][:3]
            imgs = body.find_all('img', alt=re.compile(r'chart|graph|yield|rate', re.I)) or body.find_all('img')[:2]
            images = [img.get('src') for img in imgs if img.get('src') and 'http' in img.get('src')]
            base = resp.url.rsplit('/', 1)[0] + '/' if images and images[0].startswith('/') else ''
            images = [base + img if img.startswith('/') else img for img in images]
            return {'abstract': abstract, 'images': images, 'extracts': {'keywords': keywords, 'quotes': quotes}}
    except Exception:
        return {'abstract': abstract, 'images': [], 'extracts': {'keywords': [], 'quotes': []}}

def load_feeds_from_schema(schema_path: str = "/app/schema/feeds.json") -> list[str]:
    with open(schema_path, 'r') as f:
        schema = json.load(f)
    rss_comp = schema.get('components', {}).get('rss_agg', {})
    cats = rss_comp.get('categories', {})
    enabled = rss_comp.get('enabled_categories', [])
    feeds = []
    for c in enabled:
        feeds.extend(cats.get(c, []))
    return [f for f in feeds if f.startswith("http")]

def init_schema(redis_url: str, schema_path: str = "/app/schema/feeds.json") -> bool:
    from redis import Redis as SyncRedis
    r = SyncRedis.from_url(redis_url, decode_responses=True)
    try:
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        ver = schema['version']
        deployed = r.get("rss:schema_version") or "0.0"
        if ver <= deployed:
            return True
        pipe = r.pipeline()
        for k in schema['keys']:
            key = k['name']
            if not r.exists(key):
                if k['type'] == 'SET': pipe.sadd(key, '')
                elif k['type'] == 'ZSET': pipe.zadd(key, {'placeholder': 0})
                elif k['type'] == 'STREAM': pipe.xadd(key, {'uid': 'init', 'abstract': 'ready'})
        pipe.execute()
        for key, ttl in schema.get('global_ttls', {}).items():
            r.expire(key, ttl)
        r.set("rss:schema_version", ver)
        r.bgsave()
        return True
    except Exception as e:
        print(f"Schema init failed: {e}")
        return False

async def publish_once_async(r: AsyncRedis, feeds: list[str], max_items: int, session: aiohttp.ClientSession, ua: str) -> int:
    seen_key, index_key, queue_key = "rss:seen", "rss:index", "rss:queue"
    new_total = 0
    for feed in feeds:
        print(f"Requesting feed: {feed}")
        try:
            fp = await fetch_feed_async(feed, 10, ua)
            print(f"Feed parsed: {len(fp.entries)} entries total")
            count = 0
            for e in fp.entries:
                d = normalize_entry(feed, e)
                uid = d["uid"]
                if not await r.sadd(seen_key, uid): continue
                enriched = await enrich_article_async(d['url'], d['summary'], session)
                d['abstract'] = enriched['abstract']
                d['images'] = json.dumps(enriched['images'])
                d['extracts'] = json.dumps(enriched['extracts'])
                await r.hset(f"rss:item:{uid}", mapping=d)
                await r.zadd(index_key, {uid: float(d["published_ts"])})
                await r.xadd(queue_key, {"uid": uid, "abstract": d['abstract'], "images": d['images'], "extracts": d['extracts']})
                count += 1
                new_total += 1
                if count >= max_items: break
            print(f"Processed {count} new from {feed} (after dedupe)")
        except Exception as e:
            print(f"Feed error {feed}: {e}")
    return new_total

async def main_async() -> int:
    redis_url = _env("REDIS_URL", "redis://main-redis:6379")
    r = AsyncRedis.from_url(redis_url, decode_responses=True)
    if not init_schema(redis_url):
        return 1
    # Heartbeat task
    asyncio.create_task(start_heartbeat())
    schedule = int(_env("SCHEDULE_SEC", "60"))  # 1 min
    max_per = int(_env("MAX_PER_FEED", "5"))
    ua = _env("USER_AGENT", "MarketSwarm/1.0")
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                feeds = load_feeds_from_schema()
                print(f"Polling {len(feeds)} feeds")
                new_ct = await publish_once_async(r, feeds, max_per, session, ua)
                print(f"Cycle: {new_ct} new items")
            except Exception as e:
                print(f"Cycle error: {e}", file=sys.stderr)
            await asyncio.sleep(schedule)
    return 0

if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("Shutting down gracefully", file=sys.stderr)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)