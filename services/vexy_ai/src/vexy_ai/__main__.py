from __future__ import annotations
import os, time, json, logging, signal
import redis

log = logging.getLogger("vexy_ai")

STOP = False
def _sig(*_):
    global STOP; STOP = True

def _env(name: str, default: str) -> str:
    v = os.getenv(name, default)
    return default if v is None or v.strip() == "" else v

def analyze_stub(title: str, summary: str, url: str) -> dict:
    text = (f"{title}. {summary}").strip()
    abstract = (text[:260] + "…") if len(text) > 260 else text
    bullets = [b for b in (summary.split(". ")[:3]) if b]
    tags = []
    low = text.lower()
    if any(k in low for k in ("fed","fomc","rate","inflation")): tags.append("macro")
    if "earnings" in low: tags.append("earnings")
    if any(k in low for k in ("ai","llm","model")): tags.append("ai")
    return {
        "abstract": abstract,
        "bullets": json.dumps(bullets),
        "tags": ",".join(tags),
        "sentiment": "neutral",
        "url": url,
        "ts": str(int(time.time())),
    }

def main() -> int:
    logging.basicConfig(level=_env("LOG_LEVEL","INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    signal.signal(signal.SIGTERM, _sig); signal.signal(signal.SIGINT, _sig)

    redis_url    = _env("REDIS_URL", "redis://main-redis:6379")
    stream       = _env("RSS_STREAM", "rss:queue")
    group        = _env("RSS_GROUP",  "vexy")
    consumer     = _env("RSS_CONSUMER", os.uname().nodename)
    block_ms     = int(_env("RSS_BLOCK_MS", "5000"))

    r = redis.Redis.from_url(redis_url, decode_responses=True)

    # Create group if missing
    try:
        r.xgroup_create(stream, group, id="$", mkstream=True)
        log.info("Created group %s on %s", group, stream)
    except redis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            log.info("Using existing group %s on %s", group, stream)
        else:
            raise

    log.info("vexy worker online: group=%s consumer=%s", group, consumer)

    while not STOP:
        resp = r.xreadgroup(group, consumer, streams={stream: ">"}, count=10, block=block_ms)
        if not resp:
            continue
        for _, entries in resp:
            for msg_id, fields in entries:
                uid = fields.get("uid")
                try:
                    item_key = f"rss:item:{uid}"
                    item = r.hgetall(item_key)
                    if not item:
                        log.warning("Missing item for uid=%s (ack)", uid)
                        r.xack(stream, group, msg_id)
                        continue
                    out = analyze_stub(item.get("title",""), item.get("summary",""), item.get("url",""))
                    r.hset(f"rss:analysis:{uid}", mapping=out)
                    r.zadd("rss:analysis_index", {uid: float(out["ts"])})
                    r.xack(stream, group, msg_id)
                    log.info("Analyzed uid=%s %s", uid, item.get("title","")[:80])
                except Exception as e:
                    log.exception("Failed uid=%s: %s", uid, e)
                    time.sleep(0.1)
    log.info("vexy worker stopping")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())