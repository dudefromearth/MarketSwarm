#!/usr/bin/env python3
import json
import redis
import xml.etree.ElementTree as ET
from datetime import datetime
import os


def generate_all_feeds(feeds_conf):
    """Generate all configured category RSS feeds from Redis data."""
    r = redis.Redis(host="system-redis", port=6379, decode_responses=True)
    feeds = feeds_conf.get("feeds", {})
    publish_dir = feeds_conf["workflow"].get("publish_dir", "./feeds")
    output_map = feeds_conf["workflow"].get("output_feeds", {})

    os.makedirs(publish_dir, exist_ok=True)
    print(f"\n🧩 Generating RSS feeds into {publish_dir}")

    for category, feed_list in feeds.items():
        output_name = output_map.get(category, f"{category}.xml")
        output_path = os.path.join(publish_dir, output_name)

        # Get all UIDs for this category
        uids = [uid for uid in r.zrange("rss:index", 0, -1) if r.hget(f"rss:item:{uid}", "category") == category]
        if not uids:
            print(f"⚠️  No items found for {category}, skipping.")
            continue

        # Build RSS feed
        root = ET.Element("rss", version="2.0")
        channel = ET.SubElement(root, "channel")
        ET.SubElement(channel, "title").text = f"Fed Alerts – {category.replace('_', ' ').title()}"
        ET.SubElement(channel, "link").text = "https://x.com/FOMCAlerts"
        ET.SubElement(channel, "description").text = "Curated financial and macroeconomic alerts with abstracts and images"

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
            ET.SubElement(entry, "pubDate").text = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")

        tree = ET.ElementTree(root)
        tree.write(output_path, encoding="utf-8", xml_declaration=True)
        print(f"✅ Generated {output_name} ({len(uids)} items)")

    print("🎉 All category RSS feeds generated successfully.\n")