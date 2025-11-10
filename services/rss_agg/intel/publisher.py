#!/usr/bin/env python3
import json
import redis
import xml.etree.ElementTree as ET
from datetime import datetime
import os


def generate_all_feeds(feeds_conf):
    """Generate all configured category RSS feeds from Redis data."""

    # 🧩 Redis connection (host-based, not Docker alias)
    redis_host = os.getenv("SYSTEM_REDIS_HOST", "127.0.0.1")
    redis_port = int(os.getenv("SYSTEM_REDIS_PORT", "6379"))
    r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    print(f"[debug] Connected to Redis at {redis_host}:{redis_port} for publishing")

    # 🗂 Feed configuration and output mapping
    feeds = feeds_conf.get("feeds", {})
    output_map = feeds_conf["workflow"].get("output_feeds", {})

    # 🗃 Resolve publish directory
    publish_dir = os.getenv("FEEDS_DIR") or feeds_conf["workflow"].get("publish_dir", "./feeds")
    if not os.path.isabs(publish_dir):
        publish_dir = os.path.join(os.getcwd(), publish_dir)

    os.makedirs(publish_dir, exist_ok=True)
    print(f"\n🧩 Generating RSS feeds into {publish_dir}")

    # 🌀 Generate RSS for each feed category
    for category, feed_list in feeds.items():
        output_name = output_map.get(category, f"{category}.xml")
        output_path = os.path.join(publish_dir, output_name)

        try:
            # Collect items by category
            uids = [
                uid for uid in r.zrange("rss:index", 0, -1)
                if r.hget(f"rss:item:{uid}", "category") == category
            ]
            if not uids:
                print(f"⚠️  No items found for {category}, skipping.")
                continue

            # Build RSS feed structure
            root = ET.Element("rss", version="2.0")
            channel = ET.SubElement(root, "channel")
            ET.SubElement(channel, "title").text = f"Fed Alerts – {category.replace('_', ' ').title()}"
            ET.SubElement(channel, "link").text = "https://x.com/FOMCAlerts"
            ET.SubElement(channel, "description").text = (
                "Curated financial and macroeconomic alerts with abstracts and images"
            )

            for uid in uids:
                item = r.hgetall(f"rss:item:{uid}")
                title = item.get("title", "Untitled")
                abstract = item.get("abstract", "Full details at link.")
                url = item.get("url", "")
                image = item.get("image", "")

                entry = ET.SubElement(channel, "item")
                ET.SubElement(entry, "title").text = title
                ET.SubElement(entry, "description").text = abstract
                ET.SubElement(entry, "link").text = url
                if image:
                    ET.SubElement(entry, "enclosure", url=image, type="image/jpeg", length="10000")
                ET.SubElement(entry, "pubDate").text = datetime.now().strftime(
                    "%a, %d %b %Y %H:%M:%S %z"
                )

            # Write feed to file
            tree = ET.ElementTree(root)
            tree.write(output_path, encoding="utf-8", xml_declaration=True)
            print(f"✅ Generated {output_name} ({len(uids)} items)")

        except Exception as e:
            print(f"❌ Error generating feed for {category}: {e}")

    print("🎉 All category RSS feeds generated successfully.\n")