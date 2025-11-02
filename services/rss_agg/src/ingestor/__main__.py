from __future__ import annotations
import hashlib, logging, os, time
from typing import Iterable, List, Dict
import requests, redis, feedparser
from bs4 import BeautifulSoup

log = logging.getLogger("ingestor")

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

def fetch_feed(url: str, timeout: float, ua: str) -> feedparser.FeedParserDict:
    resp = requests.get(url, headers={"User-Agent": ua}, timeout=timeout)
    resp.raise_for_status()
    return feedparser.parse(resp.content)

def normalize_entry(feed_url: str, e) -> Dict[str, str]:
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
        "published_ts": str(ts), "summary": summary,
    }

def publish_once(r: redis.Redis, feeds: Iterable[str], max_items_per_feed: int, timeout: float, ua: str) -> int:
    seen_key = "rss:seen"
    index_key = "rss:index"
    queue_key = "rss:queue"
    new_total = 0

    for feed in feeds:
        if not feed or feed.startswith("#"):  # comments/blank lines
            continue
        try:
            log.info("Fetch %s", feed)
            fp = fetch_feed(feed, timeout, ua)
        except Exception as e:
            log.warning("Fetch failed %s: %s", feed, e)
            continue
        count = 0
        for e in fp.entries:
            d = normalize_entry(feed, e)
            uid = d["uid"]
            # dedupe
            if not r.sadd(seen_key, uid):
                continue
            # store article hash
            r.hset(f"rss:item:{uid}", mapping=d)
            # time index
            r.zadd(index_key, {uid: float(d["published_ts"])})
            # enqueue for analysis
            r.xadd(queue_key, {"uid": uid, "url": d["url"], "title": d["title"], "source": d["source"]})
            count += 1
            new_total += 1
            if count >= max_items_per_feed:
                break
        log.info("Published %d new items from %s", count, feed)
    return new_total

def main() -> int:
    logging.basicConfig(level=_env("LOG_LEVEL","INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    redis_url   = _env("REDIS_URL", "redis://main-redis:6379")
    feeds_file  = _env("FEEDS_FILE", "/app/config/feeds.txt")
    schedule    = int(_env("SCHEDULE_SEC", "600"))
    timeout     = float(_env("FETCH_TIMEOUT_SEC", "8"))
    max_per     = int(_env("MAX_PER_FEED", "50"))
    ua          = _env("USER_AGENT", "MarketSwarm/1.0 (+https://your.site/contact)")

    r = redis.Redis.from_url(redis_url, decode_responses=True)
    log.info("ingestor starting: redis=%s schedule=%ss max_per_feed=%s", redis_url, schedule, max_per)

    # hot loop
    while True:
        try:
            with open(feeds_file) as f:
                feeds: List[str] = [ln.strip() for ln in f if ln.strip()]
        except Exception as e:
            log.error("Cannot read feeds file %s: %s", feeds_file, e)
            feeds = []

        new_ct = publish_once(r, feeds, max_per, timeout, ua)
        log.info("Cycle complete, new=%d", new_ct)

        # sleep in short steps for quick SIGTERM
        remaining = float(schedule)
        while remaining > 0:
            time.sleep(min(0.5, remaining))
            remaining -= 0.5
    return 0

if __name__ == "__main__":
    raise SystemExit(main())