from __future__ import annotations
import os, sys, time, logging
from .core import load_urls, run_batch_once, setup_logging

def env(n: str, d: str | None = None) -> str | None:
    v = os.getenv(n, d)
    return v if (v is None or v.strip() != "") else d

def main() -> int:
    setup_logging(level=env("LOG_LEVEL", "INFO"))
    log = logging.getLogger("rss_agg")

    feeds_file    = env("FEEDS_FILE", "/app/config/feeds.txt")
    redis_url     = env("REDIS_URL", "redis://main-redis:6379")
    timeout_sec   = float(env("FETCH_TIMEOUT_SEC", "8"))
    max_conc      = int(env("MAX_CONCURRENCY", "8"))
    user_agent    = env("USER_AGENT", "MarketSwarm/1.0 (+https://example.com/contact)")
    emit_list_key = env("EMIT_LIST_KEY", "rss:new")
    interval_sec  = float(env("POLL_INTERVAL_SEC", "0"))  # 0 = run once

    urls = load_urls(feeds_file)
    if not urls:
        log.error("No feeds found. FEEDS_FILE=%s", feeds_file)
        return 2

    def run_once():
        stats = run_batch_once(
            urls=urls,
            redis_url=redis_url,
            timeout=timeout_sec,
            max_workers=max_conc,
            user_agent=user_agent,
            emit_list_key=emit_list_key,
        )
        log.info("Cycle complete: %s", stats)

    if interval_sec <= 0:
        run_once()
        return 0

    log.info("Starting poll loop: every %ss | feeds=%d", interval_sec, len(urls))
    try:
        while True:
            run_once()
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        log.info("Shutting down (Ctrl+C)")
        return 0

if __name__ == "__main__":
    sys.exit(main())