from __future__ import annotations
import os, json, logging, hashlib
from typing import Dict, List
import redis

log = logging.getLogger("ingestor.sync_truth")

def _env(k, d):
    v = os.getenv(k, d)
    return d if v is None or str(v).strip() == "" else v

def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()

def _load_json(path: str) -> Dict:
    with open(path, "r") as f:
        return json.load(f)

def _merge(base: Dict, overlay: Dict) -> Dict:
    # shallow merge for core/secrets/components; overlay wins
    out = {**base}
    for k, v in (overlay or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out

def sync():
    logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")

    truth_file    = _env("TRUTH_FILE", "/app/root/truth.json")
    secrets_file  = _env("TRUTH_SECRETS_FILE", "/app/root/truth.secrets.json")
    redis_url     = _env("REDIS_URL", "redis://main-redis:6379")

    # feed/cat keys
    feeds_all_key    = _env("FEEDS_ALL_KEY",   "rss:feeds_all")
    feeds_key        = _env("FEEDS_KEY",       "rss:feeds")
    cats_key         = _env("CATS_KEY",        "rss:feed_categories")
    poll_key         = _env("POLL_SEC_KEY",    "cfg:ingestor:poll_interval_sec")
    enabled_cats_key = _env("ENABLED_CATS_KEY","cfg:ingestor:enabled_categories")

    r = redis.Redis.from_url(redis_url, decode_responses=True)

    truth = _load_json(truth_file)
    if os.path.exists(secrets_file):
        truth = _merge(truth, _load_json(secrets_file))

    # 1) core configs -> cfg:core:*
    for k, v in (truth.get("core") or {}).items():
        if k.endswith("_url") or isinstance(v, (str, int, float)):
            r.set(f"cfg:core:{k}", str(v))

    # 2) component configs -> cfg:component:<name>:<k>
    for comp, cfg in (truth.get("components") or {}).items():
        if not isinstance(cfg, dict): continue
        for k, v in cfg.items():
            if isinstance(v, (str, int, float)):
                r.set(f"cfg:component:{comp}:{k}", str(v))

    # 3) secrets -> secret:<scope>:<k>
    for scope, kv in (truth.get("secrets") or {}).items():
        if not isinstance(kv, dict): continue
        for k, v in kv.items():
            if isinstance(v, (str, int, float)) and str(v).strip():
                r.set(f"secret:{scope}:{k}", str(v))

    # 4) categories & feeds -> sets + unions + poll seconds + enabled categories
    comp_rss = (truth.get("components") or {}).get("ingestor") or {}
    cats = comp_rss.get("categories") or {}
    flat_feeds = comp_rss.get("feeds") or []
    enabled_cats = comp_rss.get("enabled_categories") or []
    poll_min = comp_rss.get("poll_interval_min")

    # normalize cats
    norm_cats: Dict[str, List[str]] = {}
    for name, urls in (cats or {}).items():
        if not isinstance(urls, list): continue
        u = [x.strip() for x in urls if isinstance(x, str) and x.strip()]
        if u: norm_cats[name.strip()] = u

    if not norm_cats and flat_feeds:
        norm_cats = {"default": [x.strip() for x in flat_feeds if isinstance(x, str) and x.strip()]}
        if not enabled_cats:
            enabled_cats = ["default"]

    # unions
    if r.exists(feeds_all_key): r.delete(feeds_all_key)
    if r.exists(feeds_key): r.delete(feeds_key)
    if r.exists(cats_key): r.delete(cats_key)

    all_urls, enabled_urls = set(), set()
    if norm_cats:
        r.sadd(cats_key, *list(norm_cats.keys()))
    for cat, urls in norm_cats.items():
        catset = f"rss:feeds:cat:{cat}"
        if r.exists(catset): r.delete(catset)
        if urls:
            r.sadd(catset, *urls)
            all_urls.update(urls)
            if not enabled_cats or cat in enabled_cats:
                enabled_urls.update(urls)
        for u in urls:
            uid = _sha1(u)
            meta = f"rss:feed:{uid}"
            prior = r.hget(meta, "categories") or ""
            merged = sorted(set([*(prior.split(",") if prior else []), cat]))
            r.hset(meta, mapping={"url": u, "enabled": "1", "categories": ",".join([c for c in merged if c])})

    if all_urls:
        r.sadd(feeds_all_key, *sorted(all_urls))
    if enabled_urls:
        r.sadd(feeds_key, *sorted(enabled_urls))
    elif all_urls:
        r.sadd(feeds_key, *sorted(all_urls))

    if isinstance(poll_min, int) and poll_min > 0:
        r.set(poll_key, str(poll_min * 60))
    if enabled_cats:
        r.set(enabled_cats_key, ",".join(enabled_cats))

    log.info("truth sync complete: core+components+secrets+feeds pushed")
    log.info("cats=%d all=%d enabled=%d", len(norm_cats), r.scard(feeds_all_key), r.scard(feeds_key))

if __name__ == "__main__":
    sync()