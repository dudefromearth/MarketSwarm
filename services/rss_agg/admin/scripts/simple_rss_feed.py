#!/usr/bin/env python3
import json
import redis
import xml.etree.ElementTree as ET
from datetime import datetime
import sys

# Connect
try:
    r = redis.Redis(host='localhost', port=6379, socket_timeout=5, decode_responses=True)
    r.ping()
    print("Redis connected – ready to generate")
except Exception as e:
    print(f"Redis connect failed: {e}", file=sys.stderr)
    sys.exit(1)

# Pull all uids from index
uids = r.zrange("rss:index", 0, -1)
if not uids:
    print("No items in rss:index – nothing to generate")
    sys.exit(0)

# Filter to title/abstract/url non-empty
filtered_uids = []
for uid in uids:
    item = r.hgetall(f'rss:item:{uid}')
    if item.get('title', '').strip() and item.get('abstract', '').strip() and item.get('url', '').strip():
        filtered_uids.append(uid)

if not filtered_uids:
    print("No items with title/abstract/url – nothing to generate")
    sys.exit(0)

print(f"Generated from {len(filtered_uids)} items")

root = ET.Element('rss', version='2.0')
channel = ET.SubElement(root, 'channel')
ET.SubElement(channel, 'title').text = 'FOMC Alerts – Clean Insights'
ET.SubElement(channel, 'link').text = 'https://x.com/FOMCAlerts'
ET.SubElement(channel, 'description').text = 'Clean Fed Alerts with Abstracts & Links'

for uid in filtered_uids:
    item = r.hgetall(f'rss:item:{uid}')
    title = item['title']
    abstract = item['abstract'][:140] + '...' if len(item['abstract']) > 140 else item['abstract']
    url = item['url']
    entry = ET.SubElement(channel, 'item')
    ET.SubElement(entry, 'title').text = title
    ET.SubElement(entry, 'description').text = abstract
    ET.SubElement(entry, 'link').text = url
    ET.SubElement(entry, 'pubDate').text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')
    print(f"Added {uid}")

# Write XML
tree = ET.ElementTree(root)
tree.write('./feeds/fomc_alerts.xml', encoding='utf-8', xml_declaration=True)
print("Generated ./feeds/fomc_alerts.xml with {} items – ready for dlvr.it".format(len(filtered_uids)))