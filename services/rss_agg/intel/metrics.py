# metrics.py
import redis.asyncio as redis

r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)

async def inc(key: str, amount: int = 1):
    try:
        await r.incrby(key, amount)
    except:
        pass  # metrics should NEVER break pipeline


async def add_ingestor(found=0, saved=0, rejected=0, dedup=0):
    await inc("rss:metrics:ingestor:urls_found", found)
    await inc("rss:metrics:ingestor:urls_saved", saved)
    await inc("rss:metrics:ingestor:urls_rejected", rejected)
    await inc("rss:metrics:ingestor:dedup_skipped", dedup)


async def add_canonical(success=0, network_fail=0, parse_fail=0):
    await inc("rss:metrics:canonical:canonical_success", success)
    await inc("rss:metrics:canonical:network_fail", network_fail)
    await inc("rss:metrics:canonical:parse_fail", parse_fail)


async def add_rawfetch(success=0, fail=0, blocked=0, timeouts=0):
    await inc("rss:metrics:rawfetch:http_success", success)
    await inc("rss:metrics:rawfetch:http_fail", fail)
    await inc("rss:metrics:rawfetch:blocked", blocked)
    await inc("rss:metrics:rawfetch:timeouts", timeouts)


async def add_enrich(success=0, fail=0):
    await inc("rss:metrics:enrich:success", success)
    await inc("rss:metrics:enrich:fail", fail)


async def add_publisher(feeds=0, errors=0):
    await inc("rss:metrics:publisher:feeds_written", feeds)
    await inc("rss:metrics:publisher:feed_errors", errors)