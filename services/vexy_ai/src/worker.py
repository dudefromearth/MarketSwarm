from __future__ import annotations
import os, time, json, logging, signal
import redis, requests

log = logging.getLogger("vexy_ai.worker")

def _env(name: str, default: str) -> str:
    v = os.getenv(name, default)
    return default if v is None or v.strip() == "" else v

STOP = False
def _sig(*_):
    global STOP; STOP = True

def simple_analyze(title: str, summary: str, url: str) -> dict:
    """
    Placeholder analysis:
      - 1-sentence abstract (trim)
      - 3 bullets (naive split)
      - tags (cheap heuristics)
      - sentiment (dummy)
    Swap this out for your real model/API.
    """
    text = (f"{title}. {summary}").strip()
    abstract = (text[:260] + "…") if len(text) > 260 else text
    paras = [p.strip() for p in summary.split(". ") if p.strip()]
    bullets = paras[:3]
    tags = []
    low = text.lower()
    if "fed" in low or "rates" in low or "fomc" in low: tags.append("macro")
    if "earnings" in low: tags.append("earnings")
    if "ai" in low or "llm" in low: tags.append("ai")
    sentiment = "neutral"
    return {
        "abstract": abstract,
        "bullets": json.dumps(bullets),
        "tags": ",".join(tags),
        "sentiment": sentiment,
        "url": url,
        "ts": str(int(time.time())),
    }

def run():
    logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    signal.signal(signal.SIGTERM, _sig); signal.signal(signal.SIGINT, _sig)

    redis_url    = _env("REDIS_URL", "redis://main-redis:6379")
    stream       = _env("RSS_STREAM", "rss:queue")
    group        = _env("RSS_GROUP",  "vexy")
    consumer     = _env("RSS_CONSUMER", os.uname().nodename)
    block_ms     = int(_env("RSS_BLOCK_MS", "5000"))
    r = redis.Redis.from_url(redis_url, decode_responses=True)

    # Create group if it doesn't exist
    try:
        r.xgroup_create(stream, group, id="$", mkstream=True)
        log.info("Created group %s on %s", group, stream)
    except redis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            pass
        else:
            raise

    while not STOP:
        resp = r.xreadgroup(group, consumer, streams={stream: ">"}, count=10, block=block_ms)
        if not resp:
            continue
        for _, entries in resp:
            for msg_id, fields in entries:
                uid = fields.get("uid")
                try:
                    item = r.hgetall(f"rss:item:{uid}")
                    if not item:
                        log.warning("Missing item for uid=%s", uid)
                        r.xack(stream, group, msg_id)
                        continue
                    out = simple_analyze(item.get("title",""), item.get("summary",""), item.get("url",""))
                    r.hset(f"rss:analysis:{uid}", mapping=out)
                    r.zadd("rss:analysis_index", {uid: float(out["ts"])})
                    r.xack(stream, group, msg_id)
                    log.info("Analyzed uid=%s title=%s", uid, item.get("title","")[:80])
                except Exception as e:
                    log.exception("Failed uid=%s: %s", uid, e)
                    # do not ack; it will remain pending for retry/claim
                    time.sleep(0.1)

if __name__ == "__main__":
    run()