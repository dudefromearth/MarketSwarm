from __future__ import annotations
import os, time, hashlib, logging
from typing import Iterable
import feedparser, requests, redis
from bs4 import BeautifulSoup

log = logging.getLogger("ingestor.publisher")

def _env(name: str, default: str) -> str:
    v = os.getenv(name, default)
    return default if v is None or v.strip() == "" else v

def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()

def abridge_html(html: str, max_chars: int = 800) -> str:
    if not html:
        return ""
    txt = BeautifulSoup(html, "html.parser").get_text(separator=" ").strip()
    return (txt[: max_chars - 1] + "…") if len(txt) > max_chars else txt

def normalize_entry(feed_url: str, e) -> dict:
    link = (e.get("link") or "").strip()
    guid = (e.get("id") or link or "").strip()
    uid  = sha1(guid or link or f"{feed_url}:{e.get('title','')}")
    pub  = e.get("published_parsed") or e.get("updated_parsed")
    ts   = int(time.mktime(pub)) if pub else int(time.time())
    src  = feed_url.split("/")[2] if "://" in feed_url else feed_url
    title = (e.get("title") or link or "").strip()
    summary = abridge_html(e.get("summary", ""), max_chars=800)
    return {
        "uid": uid, "url": link, "source": src, "title": title,
        "published_ts": str(ts), "summary": summary
    }

def publish(redis_url: str, feeds: Iterable[str], max_items_per_feed: int = 50):
    r = redis.Redis.from_url(redis_url, decode_responses=True)
    seen_key = "rss:seen"
    index_key = "rss:index"
    queue_key = "rss:queue"

    for feed in feeds:
        if not feed or feed.startswith("#"):
            continue
        log.info("Fetch %s", feed)
        fp = feedparser.parse(feed)
        count = 0
        for e in fp.entries:
            d = normalize_entry(feed, e)
            uid = d["uid"]
            # dedupe
            if not r.sadd(seen_key, uid):
                continue
            # store article hash
            r.hset(f"rss:item:{uid}", mapping=d)
            # index by time
            r.zadd(index_key, {uid: float(d["published_ts"])})
            # enqueue work item
            r.xadd(queue_key, {"uid": uid, "url": d["url"], "title": d["title"], "source": d["source"]})
            count += 1
            if count >= max_items_per_feed:
                break
        log.info("Published %d new items from %s", count, feed)

def main():
    import logging, sys
    logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    redis_url = _env("REDIS_URL", "redis://main-redis:6379")
    feeds_file = _env("FEEDS_FILE", "/app/config/feeds.txt")
    max_items = int(_env("MAX_PER_FEED", "50"))
    with open(feeds_file) as f:
        feeds = [ln.strip() for ln in f if ln.strip()]
    publish(redis_url, feeds, max_items)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())