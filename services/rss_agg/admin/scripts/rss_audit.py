import json
import sys
import datetime
from collections import defaultdict, Counter
from redis import Redis


def _env(name: str, default: str) -> str:
    import os
    v = os.getenv(name)
    return default if v is None or v.strip() == "" else v


def connect_redis() -> Redis:
    redis_url = _env("REDIS_URL", "redis://main-redis:6379")
    return Redis.from_url(redis_url, decode_responses=True)


def fetch_quarantine_items(r: Redis, count: int = 50):
    items = r.xrevrange("rss:quarantine", count=count)
    results = []
    for sid, data in items:
        data["stream_id"] = sid
        data["timestamp"] = datetime.datetime.fromtimestamp(
            int(sid.split('-')[0]) / 1000
        ).isoformat()
        results.append(data)
    return results


def summarize_quarantine(items):
    domains = defaultdict(list)
    for item in items:
        url = item.get("url", "")
        domain = url.split("/")[2] if "//" in url else "unknown"
        domains[domain].append(item)

    summary = []
    for domain, entries in domains.items():
        reasons = Counter([e.get("reason", "unknown") for e in entries])
        summary.append(
            {
                "domain": domain,
                "count": len(entries),
                "reasons": dict(reasons),
                "latest": entries[0].get("timestamp"),
            }
        )
    summary.sort(key=lambda x: x["count"], reverse=True)
    return summary


def print_report(summary, limit=10):
    print("\n🧭 Quarantine Audit Report")
    print("=" * 80)
    for s in summary[:limit]:
        print(f"Domain: {s['domain']}")
        print(f"  Items: {s['count']}")
        print(f"  Reasons: {json.dumps(s['reasons'])}")
        print(f"  Latest: {s['latest']}")
        print("-" * 80)


def export_json(summary, path="/tmp/rss_quarantine_audit.json"):
    with open(path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"✅ Report exported to {path}")


def main():
    r = connect_redis()
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    items = fetch_quarantine_items(r, count)
    if not items:
        print("No quarantined items found.")
        return
    summary = summarize_quarantine(items)
    print_report(summary)

    if "--export" in sys.argv:
        export_json(summary)


if __name__ == "__main__":
    main()