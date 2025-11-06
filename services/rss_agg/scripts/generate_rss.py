#!/usr/bin/env python3
"""
Generate RSS feed from RSS Agg index or queue.
Usage: python generate_rss.py [-f] [-m] [-c N] [-s H] [-q] [-h]

- -f: Full items only.
- -m: Minimal items only.
- -c N: Count (default 5).
- -s H: Since hours (default none).
- -q: From queue.
- -h: Help.
Output: ./feeds/fomc_alerts.xml.
"""

import json
import redis
import xml.etree.ElementTree as ET
from datetime import datetime
import argparse
import time
import sys

# Connect with timeout
try:
    r = redis.Redis(host='localhost', port=6379, socket_timeout=5, decode_responses=True)
    r.ping()  # Test connect
    print("Redis connected – ready to generate")
except Exception as e:
    print(f"Redis connect failed: {e}", file=sys.stderr)
    sys.exit(1)

# Parse args
parser = argparse.ArgumentParser(description="Generate RSS feed from RSS Agg data.")
parser.add_argument("-f", "--full", action="store_true")
parser.add_argument("-m", "--minimal", action="store_true")
parser.add_argument("-c", type=int, default=5)
parser.add_argument("-s", type=int)
parser.add_argument("-q", "--from-queue", action="store_true")
args = parser.parse_args()

# Pull uids
if args.from_queue:
    stream_entries = r.xread({'rss:queue': '$'}, count=args.c, block=0)
    if not stream_entries:
        print("No new items in rss:queue – nothing to generate")
        sys.exit(0)
    uids = [data['uid'] for stream, messages in stream_entries for data in messages]
    for stream, messages in stream_entries:
        for message_id, data in messages:
            r.xdel('rss:queue', message_id)
else:
    uids = r.zrange("rss:index", 0, args.c - 1)
    if args.s:
        cutoff = time.time() - (args.s * 3600)
        uids = [uid for uid in uids if float(r.zscore("rss:index", uid)) > cutoff]

if not uids:
    print("No items found – nothing to generate")
    sys.exit(0)

# Filter uids (full or minimal)
filtered_uids = []
required = ['title', 'url', 'abstract']
optional = ['images', 'extracts']
all_attrs = required + optional
for uid in uids:
    item = r.hgetall(f'rss:item:{uid}')
    if args.full:
        if all(attr in item and item[attr].strip() for attr in all_attrs):
            filtered_uids.append(uid)
    elif args.minimal:
        if all(attr in item and item[attr].strip() for attr in required):
            filtered_uids.append(uid)
    else:
        filtered_uids.append(uid)

if not filtered_uids:
    print("No items match filter – nothing to generate")
    sys.exit(0)

print(f"Generated from {len(filtered_uids)} items after filter")

root = ET.Element('rss', version='2.0')
channel = ET.SubElement(root, 'channel')
ET.SubElement(channel, 'title').text = 'FOMC Alerts – Clean Insights'
ET.SubElement(channel, 'link').text = 'https://x.com/FOMCAlerts'
ET.SubElement(channel, 'description').text = 'Clean Fed Alerts with Abstracts & Images'

for uid in filtered_uids:
    item = r.hgetall(f'rss:item:{uid}')
    title = item.get('title', 'FOMC Alert')
    abstract = item.get('abstract', '')[:140] + '...' if item.get('abstract') else 'Full details at link.'
    url = item.get('url', '')
    images = json.loads(item.get('images', '[]'))
    image_url = images[0] if images else ''
    entry = ET.SubElement(channel, 'item')
    ET.SubElement(entry, 'title').text = title
    ET.SubElement(entry, 'description').text = abstract
    ET.SubElement(entry, 'link').text = url
    if image_url:
        ET.SubElement(entry, 'enclosure', url=image_url, type='image/jpeg', length='10000')
    ET.SubElement(entry, 'pubDate').text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')
    print(f"Added {uid} to RSS feed")

# Write XML to file
tree = ET.ElementTree(root)
tree.write('./feeds/fomc_alerts.xml', encoding='utf-8', xml_declaration=True)
print("Generated ./feeds/fomc_alerts.xml with {} items – ready for dlvr.it".format(len(filtered_uids)))