# services/rss_agg/src/ingestor/__main__.py
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Dict, Iterable, List

import feedparser
import redis
import requests
from bs4 import BeautifulSoup

from shared.logit import Logit

# ---- module identity / logger -------------------------------------------------
MODULE = os.getenv("MODULE_NAME", "ingestor")
SERVICE_ID = os.getenv("SERVICE_ID", "rss_agg")
log = Logit(MODULE, SERVICE_ID)  # positional args

# ---- helpers ------------------------------------------------------------------
def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return default if v is None or v.strip() == "" else v

def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()

def abridge_html(html: str, max_chars: int = 800) -> str:
    if not html:
        return ""
    txt = BeautifulSoup(html, "html.parser").get_text(separator=" ").strip()
    return (txt[: max_chars - 1] + "…") if len(txt) > max_chars else txt

# Characters that sometimes sneak into pasted URLs
_INVIS = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)

def clean_url(u: str) -> str:
    if not isinstance(u, str):
        return ""
    # drop zero-widths and strip whitespace
    return u.translate(_INVIS).strip()

def fetch_feed(url: str, timeout: float, ua: str, retries: int = 2, backoff: float = 0.7) -> feedparser.FeedParserDict:
    last_err = None
    url = clean_url(url)
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers={"User-Agent": ua}, timeout=timeout)
            resp.raise_for_status()
            return feedparser.parse(resp.content)
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                sleep_s = backoff * (attempt + 1)
                log.debug(f"Retry {attempt+1}/{retries} after {sleep_s:.1f}s for {url}: {e}")
                time.sleep(sleep_s)
            else:
                raise last_err

def normalize_entry(feed_url: str, e) -> Dict[str, str]:
    link = clean_url(e.get("link") or "")
    guid = clean_url(e.get("id") or link or "")
    uid = sha1(guid or link or f"{feed_url}:{e.get('title','')}")
    pub = e.get("published_parsed") or e.get("updated_parsed")
    ts = int(time.mktime(pub)) if pub else int(time.time())
    src = feed_url.split("/")[2] if "://" in feed_url else feed_url
    title = (e.get("title") or link or "").strip()
    summary = abridge_html(e.get("summary", ""), max_chars=800)
    return {
        "uid": uid,
        "url": link,
        "source": src,
        "title": title,
        "published_ts": str(ts),
        "summary": summary,
    }

# ---- truth integration --------------------------------------------------------
def load_feeds_from_truth(r: redis.Redis, service_id: str, truth_key: str = "truth:doc") -> List[str]:
    """Resolve feed URLs from truth:doc for the given service."""
    raw = r.get(truth_key)
    if not raw:
        log.error(f"No truth found at {truth_key}")
        return []
    try:
        T = json.loads(raw)
    except Exception as e:
        log.error(f"Failed to parse {truth_key}: {e}")
        return []

    comp = r.hget(f"svc:cfg:{service_id}", "component") or service_id
    cfg = (T.get("components") or {}).get(comp, {}) or {}

    feeds: List[str] = []
    enabled = cfg.get("enabled_categories") or []
    cats = cfg.get("categories") or {}
    for c in enabled:
        feeds.extend(cats.get(c, []))

    if not feeds and "feeds" in cfg:
        feeds = list(cfg.get("feeds") or [])

    out, seen = [], set()
    for f in feeds:
        f2 = clean_url(f)
        if f2.startswith(("http://", "https://")) and f2 not in seen:
            seen.add(f2)
            out.append(f2)
    return out

# ---- core publish loop --------------------------------------------------------
def publish_once(
    r: redis.Redis,
    feeds: Iterable[str],
    max_items_per_feed: int,
    timeout: float,
    ua: str,
) -> int:
    seen_key = "rss:seen"
    index_key = "rss:index"
    queue_key = "rss:queue"
    new_total = 0

    for feed in feeds:
        try:
            log.info(f"Fetch {feed}")
            fp = fetch_feed(feed, timeout, ua)
        except Exception as e:
            log.warning(f"Fetch failed {feed}: {e}")
            continue

        count = 0
        for e in fp.entries:
            d = normalize_entry(feed, e)
            uid = d["uid"]

            if not r.sadd(seen_key, uid):  # dedupe
                continue

            r.hset(f"rss:item:{uid}", mapping=d)                     # store
            r.zadd(index_key, {uid: float(d["published_ts"])})       # index
            r.xadd(queue_key, {"uid": uid, "url": d["url"],          # enqueue
                               "title": d["title"], "source": d["source"]})

            count += 1
            new_total += 1
            if count >= max_items_per_feed:
                break

        log.info(f"Published {count} new items from {feed}")

    return new_total

# ---- entrypoint ---------------------------------------------------------------
def main() -> int:
    redis_url = _env("REDIS_URL", _env("REDIS_MAIN_URL", "redis://main-redis:6379"))
    truth_key = _env("TRUTH_REDIS_KEY", "truth:doc")
    schedule = int(_env("SCHEDULE_SEC", "600"))
    timeout = float(_env("FETCH_TIMEOUT_SEC", "8"))
    max_per = int(_env("MAX_PER_FEED", "50"))
    ua = _env("USER_AGENT", "MarketSwarm/1.0 (+https://your.site/contact)")

    r = redis.Redis.from_url(redis_url, decode_responses=True)
    log.info(f"{MODULE} starting: redis={redis_url} schedule={schedule}s max_per_feed={max_per}")

    while True:
        try:
            feeds = load_feeds_from_truth(r, SERVICE_ID, truth_key=truth_key)
            if not feeds:
                log.error(f"No feeds resolved from {truth_key} for service '{SERVICE_ID}'. Skipping cycle.")
            else:
                log.info(f"Resolved {len(feeds)} feeds from truth for {SERVICE_ID}")
                new_ct = publish_once(r, feeds, max_per, timeout, ua)
                log.success(f"Cycle complete, new={new_ct}")
        except Exception as e:
            log.error(f"Ingest cycle error: {e}")

        remaining = float(schedule)  # cooperative sleep
        while remaining > 0:
            time.sleep(min(0.5, remaining))
            remaining -= 0.5

if __name__ == "__main__":
    raise SystemExit(main())