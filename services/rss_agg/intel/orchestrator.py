#!/usr/bin/env python3
"""
MarketSwarm Orchestrator — Synchronous Pipeline with Stage Switches + Ledger Awareness
-------------------------------------------------------------------------------------
A clean, deterministic pipeline that runs one stage at a time.

Pipeline:
 1. ingest feeds        (RSS → category URL sets)
 2. canonical fetch     (URL → canonical markdown articles)
 3. enrich              (LLM Tier-3 metadata)
 4. publish             (RSS XML per category, transaction ledger)
 5. stats               (system counters)

All stages are synchronous.
Publisher now uses a 3-day transaction ledger to ensure correctness.
Orchestrator reports ledger status when publishing is invoked.
"""

import os
import time
import redis

# ----- Pipeline stage imports -----
from .ingestor import ingest_feeds
from .canonical_fetcher import canonical_fetcher_run_once
from .article_enricher import enrich_articles_lifo
from .publisher import generate_all_feeds
from .stats import generate_stats


PIPELINE_MODE = os.getenv("PIPELINE_MODE", "full").lower()
FORCE_INGEST = os.getenv("FORCE_INGEST", "false").lower() == "true"

# ------------------------------------------------------------
# Stage switches (0 or 1)
# ------------------------------------------------------------
def flag(name, default=1):
    """Read 0/1 environment switches safely."""
    return os.getenv(name, str(default)).strip() == "1"

PIPELINE_INGEST     = flag("PIPELINE_INGEST",     1)
PIPELINE_CANONICAL  = flag("PIPELINE_CANONICAL",  1)
PIPELINE_ENRICH     = flag("PIPELINE_ENRICH",     1)
PIPELINE_PUBLISH    = flag("PIPELINE_PUBLISH",    1)
PIPELINE_STATS      = flag("PIPELINE_STATS",      1)


# ------------------------------------------------------------
# Stage runners — all synchronous
# ------------------------------------------------------------
def run_ingest(feeds_cfg):
    print("\n[INGEST] 📡 ingest_feeds()")
    ingest_feeds(feeds_cfg)
    print("[INGEST] ✔ complete\n")


def run_canonical():
    print("[CANON] 🧱 canonical_fetcher_run_once()")
    canonical_fetcher_run_once()
    print("[CANON] ✔ complete\n")


def run_enrich():
    print("[ENRICH] 🧠 enrich_articles_lifo()")
    enrich_articles_lifo()   # fully synchronous
    print("[ENRICH] ✔ complete\n")


def run_publish(publish_dir):
    print("[PUBLISH] 📰 generate_all_feeds() (ledger-aware)")
    generate_all_feeds(publish_dir)
    print("[PUBLISH] ✔ complete\n")


def run_stats():
    print("[STATS] 📊 generate_stats()")
    generate_stats()
    print("[STATS] ✔ complete\n")


# ------------------------------------------------------------
# Optional: ledger debugging helper
# ------------------------------------------------------------
def debug_ledger_state(redis_conn):
    """
    Print ledger entries so the operator can see what categories
    have been published recently.

    This is informational only — publisher performs all logic.
    """
    print("[ledger] 📘 Checking publish ledgers…")

    keys = redis_conn.keys("rss:publish_ledger:*")
    if not keys:
        print("[ledger] (none) no ledger keys found\n")
        return

    for key in keys:
        category = key.split(":", 2)[2]
        latest = redis_conn.zrevrange(key, 0, 0, withscores=True)
        if latest:
            _, ts = latest[0]
            print(f"[ledger] {category}: last_publish_ts={ts}")
        else:
            print(f"[ledger] {category}: (empty ledger)")

    print("")


# ------------------------------------------------------------
# Orchestrator entrypoint (now with 5-minute loop)
# ------------------------------------------------------------
def run_orchestrator(svc: str, setup_info: dict, truth: dict):

    print("\n──────────────────────────────")
    print(" Orchestrator Stage Switches")
    print("──────────────────────────────")
    print(f"  INGEST:     {PIPELINE_INGEST}")
    print(f"  CANONICAL:  {PIPELINE_CANONICAL}")
    print(f"  ENRICH:     {PIPELINE_ENRICH}")
    print(f"  PUBLISH:    {PIPELINE_PUBLISH}")
    print(f"  STATS:      {PIPELINE_STATS}")
    print("──────────────────────────────\n")

    feeds_cfg = setup_info["feeds_cfg"]
    publish_dir = truth["components"][svc]["workflow"]["publish_dir"]

    # Validate intel-redis
    intel_info = setup_info["intel_redis"]
    r = redis.Redis(
        host=intel_info["host"],
        port=intel_info["port"],
        decode_responses=True
    )
    try:
        r.ping()
        print(f"[orchestrator] ✔ Connected to intel-redis {intel_info['host']}:{intel_info['port']}")
    except Exception as e:
        raise ConnectionError(f"Could not connect to intel-redis: {e}")

    # --------------------------------------------------------
    # MODE-SPECIFIC OVERRIDES (no looping)
    # --------------------------------------------------------
    if PIPELINE_MODE == "ingest_only":
        run_ingest(feeds_cfg)
        return

    if PIPELINE_MODE == "canonical_only":
        run_canonical()
        return

    if PIPELINE_MODE == "enrich_only":
        run_enrich()
        return

    if PIPELINE_MODE == "publish_only":
        run_publish(publish_dir)
        return

    if PIPELINE_MODE == "stats_only":
        run_stats()
        return

    # --------------------------------------------------------
    # FULL PIPELINE LOOP — runs forever (5-minute interval)
    # --------------------------------------------------------
    while True:
        print("\n[orchestrator] 🔥 FULL PIPELINE START\n")
        print(f"[orchestrator] 🚀 Starting (mode={PIPELINE_MODE}, force={FORCE_INGEST})")

        if PIPELINE_INGEST:
            run_ingest(feeds_cfg)

        if PIPELINE_CANONICAL:
            run_canonical()

        if PIPELINE_ENRICH:
            run_enrich()

        if PIPELINE_PUBLISH:
            run_publish(publish_dir)

        if PIPELINE_STATS:
            run_stats()

        print("\n[orchestrator] 🎉 FULL PIPELINE CYCLE COMPLETE\n")
        print("[orchestrator] ⏳ Sleeping 300 seconds before next cycle...\n")

        time.sleep(300)   # <-- 5 MINUTES

