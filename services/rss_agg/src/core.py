from __future__ import annotations
import hashlib, json, logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, Any, Dict

import feedparser, redis, requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("ingestor")

def setup_logging(level: str | int = "INFO") -> None:
    lvl = getattr(logging, str(level).upper(), logging.INFO) if isinstance(level, str) else level
    logging.basicConfig(level=lvl, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

def load_urls(feeds_file: str) -> list[str]:
    p = Path(feeds_file)
    if not p.exists():
        log.warning("Feeds file does not exist: %s", feeds_file)
        return []
    return [ln.strip() for ln in p.read_text().splitlines() if ln.strip() and not ln.startswith("#")]

def _sha1(s: str) -> str: return hashlib.sha1(s.encode()).hexdigest()

def _retrying_session(user_agent: str, timeout: float) -> requests.Session:
    s = requests.Session()
    s.trust_env = True
    s.headers.update({"User-Agent": user_agent, "Accept": "*/*"})
    retry = Retry(total=4, connect=4, read=4, backoff_factor=0.7,
                  status_forcelist=(429, 500, 502, 503, 504),
                  respect_retry_after_header=True)
    adapter = HTTPAdapter(max_retries=retry, pool_connections=64, pool_maxsize=64)
    s.mount("http://", adapter); s.mount("https://", adapter)
    orig = s.request
    def wrapped(method, url, **kw):
        kw.setdefault("timeout", timeout)
        return orig(method, url, **kw)
    s.request = wrapped
    return s

class Store:
    def __init__(self, redis_url: str):
        self.r = redis.from_url(redis_url, decode_responses=True)

    def feed_key(self, url: str) -> str: return "feed:" + _sha1(url)
    def seen_key(self, url: str) -> str: return "feed_seen:" + _sha1(url)

    def cond_headers(self, url: str) -> dict:
        key = self.feed_key(url)
        h = {}
        et = self.r.hget(key, "etag")
        lm = self.r.hget(key, "last_modified")
        if et: h["If-None-Match"] = et
        if lm: h["If-Modified-Since"] = lm
        return h

    def save_conditionals(self, url: str, resp: requests.Response) -> None:
        key = self.feed_key(url)
        pipe = self.r.pipeline()
        if (et := resp.headers.get("ETag")): pipe.hset(key, "etag", et)
        if (lm := resp.headers.get("Last-Modified")): pipe.hset(key, "last_modified", lm)
        pipe.execute()

def _entry_id(e: Any) -> str:
    eid = getattr(e, "id", None) or getattr(e, "guid", None) or getattr(e, "link", None)
    if eid: return eid
    payload = {"t": getattr(e, "title", ""), "l": getattr(e, "link", ""),
               "p": getattr(e, "published", "") or getattr(e, "updated", "")}
    return _sha1(json.dumps(payload, sort_keys=True))

def _dedupe_new(store: Store, url: str, entries: Iterable[Any]) -> list[dict]:
    out = []
    seen = store.seen_key(url)
    for e in entries:
        eid = _entry_id(e)
        if store.r.sadd(seen, eid):  # 1 => newly added
            out.append({
                "id": eid,
                "title": getattr(e, "title", ""),
                "link": getattr(e, "link", ""),
                "published": getattr(e, "published", "") or getattr(e, "updated", ""),
                "summary": getattr(e, "summary", "")[:1000],
            })
    store.r.expire(seen, 30 * 24 * 3600)
    return out

def fetch_one(url: str, user_agent: str, timeout: float, store: Store) -> list[dict]:
    s = _retrying_session(user_agent, timeout)
    try:
        resp = s.get(url, headers=store.cond_headers(url))
        if resp.status_code == 304:
            log.debug("[304] %s", url)
            return []
        resp.raise_for_status()
        store.save_conditionals(url, resp)
        parsed = feedparser.parse(resp.content)
        new_items = _dedupe_new(store, url, parsed.entries or [])
        log.info("[200] %s new=%d total=%d", url, len(new_items), len(parsed.entries or []))
        return new_items
    except requests.RequestException as e:
        log.warning("[NET] %s :: %s", url, e)
        return []
    except Exception as e:
        log.exception("[PARSE] %s :: %s", url, e)
        return []

def emit_items(store: Store, items: list[dict], list_key: str) -> int:
    if not items: return 0
    pipe = store.r.pipeline()
    for it in items: pipe.rpush(list_key, json.dumps(it, ensure_ascii=False))
    pipe.execute()
    return len(items)

def run_batch_once(
    urls: list[str],
    redis_url: str,
    timeout: float,
    max_workers: int,
    user_agent: str,
    emit_list_key: str,
) -> Dict[str, int]:
    store = Store(redis_url)
    total_new, per_feed = 0, {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        fut = {ex.submit(fetch_one, u, user_agent, timeout, store): u for u in urls}
        for f in as_completed(fut):
            u = fut[f]
            items = f.result()
            per_feed[u] = len(items)
            if items:
                total_new += emit_items(store, items, emit_list_key)
    return {"feeds": len(urls), "new_items_emitted": total_new, "per_feed": len(per_feed)}