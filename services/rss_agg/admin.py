#!/usr/bin/env python3
import json, os, sys
import redis
from typing import Optional

def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return default if v is None or v.strip() == "" else v

def R(url: str | None = None):
    url = url or _env("REDIS_URL", "redis://localhost:6379")
    try:
        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        print(f"Redis connect failed: {url}", file=sys.stderr)
        sys.exit(1)

def inspect_schema():
    r = R()
    ver = r.get("rss:schema_version") or "Not initialized"
    keys = r.keys("rss:*")
    print(f"Schema Version: {ver}")
    print(f"Keys: {list(keys)}")
    for key in keys:
        if key == "rss:index":
            print(f"{key}: {r.zrange(key, 0, -1)} (sample)")
        elif key == "rss:queue":
            print(f"{key}: Length {r.xlen(key)}")

def edit_schema(version: str = None, path: str = "schema/feeds.json"):
    r = R()
    if version:
        path = f"schema/schema_v{version}.json"
    if not os.path.exists(path):
        print(f"Schema {path} not found")
        return
    with open(path, 'r') as f:
        schema = json.load(f)
    pipe = r.pipeline()
    for k in schema['keys']:
        key = k['name']
        if k['type'] == 'SET': pipe.sadd(key, '')
        elif k['type'] == 'ZSET': pipe.zadd(key, {'placeholder': 0})
        elif k['type'] == 'STREAM': pipe.xadd(key, {'uid': 'init', 'abstract': 'ready'})
    pipe.execute()
    r.set("rss:schema_version", schema['version'])
    r.bgsave()
    print(f"Schema edited/loaded: v{schema['version']}")

def analytics():
    r = R()
    total_items = r.zcard("rss:index")
    if total_items == 0:
        print("No items stored yet.")
        return
    uids = r.zrange("rss:index", 0, -1)
    full_count = 0
    attr_counts = []
    required_attrs = ['title', 'url', 'abstract']
    optional_attrs = ['images', 'extracts']
    all_attrs = required_attrs + optional_attrs
    for uid in uids:
        item = r.hgetall(f"rss:item:{uid}")
        attrs_present = [attr for attr in all_attrs if attr in item and item[attr].strip()]
        attr_count = len(attrs_present)
        attr_counts.append(attr_count)
        if all(attr in item and item[attr].strip() for attr in required_attrs):
            full_count += 1
    completeness_pct = (full_count / total_items * 100) if total_items > 0 else 0
    avg_attrs = sum(attr_counts) / total_items if total_items > 0 else 0
    print(f"Total Items Stored: {total_items}")
    print(f"Full Completeness (required attrs): {full_count}/{total_items} ({completeness_pct:.1f}%)")
    print(f"Average Attributes/Item: {avg_attrs:.1f}/5")
    print("\nSample Item (Latest):")
    latest_uid = uids[-1]
    sample = r.hgetall(f"rss:item:{latest_uid}")
    for attr, value in sample.items():
        print(f"  {attr}: {value[:100]}...")

def okitems():
    r = R()
    total_items = r.zcard("rss:index")
    if total_items == 0:
        print("No items stored yet.")
        return
    uids = r.zrange("rss:index", 0, -1)
    min_attrs = ['title', 'url', 'abstract']
    complete_count = 0
    complete_list = []
    for uid in uids:
        item = r.hgetall(f"rss:item:{uid}")
        if all(attr in item and item[attr].strip() for attr in min_attrs):
            complete_count += 1
            complete_list.append((uid, item))
    completeness_pct = (complete_count / total_items * 100) if total_items > 0 else 0
    print(f"Total Items: {total_items}")
    print(f"Complete (title + abstract + url): {complete_count}/{total_items} ({completeness_pct:.1f}%)")
    print("\nComplete Items:")
    for uid, item in complete_list:
        print(f"UID: {uid}")
        print(f"  Title: {item.get('title', 'N/A')}")
        print(f"  URL: {item.get('url', 'N/A')}")
        print(f"  Abstract: {item.get('abstract', 'N/A')[:150]}...")
        print("---")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python admin.py [inspect|edit [version]|analytics|okitems]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "inspect":
        inspect_schema()
    elif cmd == "edit":
        ver = sys.argv[2] if len(sys.argv) > 2 else None
        edit_schema(ver)
    elif cmd == "analytics":
        analytics()
    elif cmd == "okitems":
        okitems()
    else:
        print("Command not found")