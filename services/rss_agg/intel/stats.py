#!/usr/bin/env python3
import time
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import redis

REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6381

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def human_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def count_set(pattern: str) -> int:
    keys = r.keys(pattern)
    total = 0
    for k in keys:
        total += r.scard(k)
    return total


def count_hash(pattern: str) -> int:
    keys = r.keys(pattern)
    return len(keys)


def count_zset(pattern: str) -> int:
    keys = r.keys(pattern)
    total = 0
    for k in keys:
        total += r.zcard(k)
    return total


# ------------------------------------------------------------
# Ledger analysis (3-day horizon)
# ------------------------------------------------------------
def get_publish_ledger() -> dict:
    """
    Reads:
        rss:publish_ledger:<category>

    Returns:
        {
            "categories": {
                "econ_reports": {
                    "entries": 12,
                    "last_ts": 1234567890,
                    "entries_last_3d": 5
                },
                ...
            },
            "total_ledgers": 5,
            "total_entries": 123
        }
    """
    ledgers = r.keys("rss:publish_ledger:*")
    out = {
        "categories": {},
        "total_ledgers": len(ledgers),
        "total_entries": 0,
    }

    now = time.time()
    horizon = now - (3 * 86400)  # 3 days

    for key in ledgers:
        category = key.split(":", 2)[2]

        # get all entries (timestamps)
        timestamps = r.zrange(key, 0, -1, withscores=True)
        ts_list = [ts for (_, ts) in timestamps]

        last_ts = ts_list[-1] if ts_list else None
        entries_last_3d = len([ts for ts in ts_list if ts >= horizon])

        out["categories"][category] = {
            "entries": len(ts_list),
            "last_ts": last_ts,
            "entries_last_3d": entries_last_3d,
        }

        out["total_entries"] += len(ts_list)

    return out


# ------------------------------------------------------------
# Gather stats
# ------------------------------------------------------------
def get_stats() -> dict:
    stats = {}

    # Tier-0
    stats["links_total"] = r.scard("rss:all_links")
    stats["seen_total"] = r.scard("rss:seen")

    # link sets
    keys = r.keys("rss:category_links:*")
    stats["category_link_sets"] = len(keys)
    stats["category_link_items"] = count_set("rss:category_links:*")

    # canonical
    stats["canonical_articles"] = count_hash("rss:article_canonical:*")
    stats["canonical_index"] = r.zcard("rss:article_canonical_index")

    # raw
    stats["raw_articles"] = count_hash("rss:article_raw:*")

    # enriched
    stats["enriched_articles"] = count_hash("rss:article:*")

    # per-category counts
    stats["categories"] = {}
    cat_keys = r.keys("rss:articles_by_category:*")
    for key in cat_keys:
        cat = key.split(":")[-1]
        stats["categories"][cat] = r.scard(key)

    # ledger
    stats["ledger"] = get_publish_ledger()

    return stats


# ------------------------------------------------------------
# Print to console
# ------------------------------------------------------------
def print_stats(stats: dict):
    print("\n────────────────────────────────────────────")
    print("          MarketSwarm — Redis Stats")
    print("────────────────────────────────────────────")
    print(f" Total unique links:         {stats['links_total']}")
    print(f" Total seen URLs:            {stats['seen_total']}")
    print(f" Categories discovered:      {stats['category_link_sets']}")
    print(f" Total category URLs:        {stats['category_link_items']}")
    print(f" Raw articles stored:        {stats['raw_articles']}")
    print(f" Canonical articles:         {stats['canonical_articles']}")
    print(f" Enriched articles:          {stats['enriched_articles']}")
    print(f" Canonical index entries:    {stats['canonical_index']}")

    print("\nPer-category article counts:")
    for cat, cnt in stats["categories"].items():
        print(f"   • {cat}: {cnt}")

    # ---------------- Ledger output ----------------
    ledger = stats["ledger"]
    print("\n────────────────────────────────────────────")
    print("           Publish Ledger Activity")
    print("────────────────────────────────────────────")
    print(f" Ledger keys found:          {ledger['total_ledgers']}")
    print(f" Total ledger entries:       {ledger['total_entries']}")

    for cat, info in ledger["categories"].items():
        last_ts = info["last_ts"]
        last_ts_str = human_ts(last_ts) if last_ts else "(none)"
        print(f"\n  [{cat}]")
        print(f"    entries total:          {info['entries']}")
        print(f"    last publish:           {last_ts_str}")
        print(f"    entries last 3 days:    {info['entries_last_3d']}")

    print("────────────────────────────────────────────\n")


# ------------------------------------------------------------
# Write RSS stats feed
# ------------------------------------------------------------
def generate_stats_xml(stats: dict, output_file: str):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "MarketSwarm Stats"
    ET.SubElement(channel, "link").text = "file:///stats.xml"
    ET.SubElement(channel, "description").text = "Live system statistics from Redis"
    ET.SubElement(channel, "pubDate").text = datetime.now(timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )

    def add_item(key, value):
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = key
        ET.SubElement(item, "description").text = str(value)
        ET.SubElement(item, "guid").text = key
        ET.SubElement(item, "pubDate").text = datetime.now(timezone.utc).strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )

    # Basic stats
    add_item("links_total", stats["links_total"])
    add_item("seen_total", stats["seen_total"])
    add_item("raw_articles", stats["raw_articles"])
    add_item("canonical_articles", stats["canonical_articles"])
    add_item("enriched_articles", stats["enriched_articles"])
    add_item("canonical_index", stats["canonical_index"])

    for cat, cnt in stats["categories"].items():
        add_item(f"category:{cat}", cnt)

    # Ledger output
    ledger = stats["ledger"]

    add_item("ledger:total_ledgers", ledger["total_ledgers"])
    add_item("ledger:total_entries", ledger["total_entries"])

    for cat, info in ledger["categories"].items():
        add_item(f"publish_ledger:{cat}:last_ts", info["last_ts"])
        add_item(f"publish_ledger:{cat}:entries_last_3d", info["entries_last_3d"])
        add_item(f"publish_ledger:{cat}:entries_total", info["entries"])

    xml_str = ET.tostring(rss, encoding="utf-8")
    with open(output_file, "wb") as f:
        f.write(xml_str)

    print(f"📄 stats.xml written → {output_file}")


# ------------------------------------------------------------
# Orchestrator-facing API (synchronous)
# ------------------------------------------------------------
def generate_stats():
    """
    Orchestrator calls this synchronously.
    Gathers stats → prints → writes stats.xml.
    """
    stats = get_stats()
    print_stats(stats)

    output_file = "/Users/ernie/Sites/feeds/stats.xml"
    generate_stats_xml(stats, output_file)


# ------------------------------------------------------------
# CLI entrypoint
# ------------------------------------------------------------
if __name__ == "__main__":
    generate_stats()