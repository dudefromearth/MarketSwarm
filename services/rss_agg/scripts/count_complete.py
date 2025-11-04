import redis

r = redis.Redis(host='localhost', port=6379, decode_responses=True)
uids = r.zrange("rss:index", 0, -1)
total = len(uids)
complete = 0
for uid in uids:
    item = r.hgetall(f"rss:item:{uid}")
    if 'title' in item and item['title'].strip() and 'abstract' in item and item['abstract'].strip() and 'url' in item and item['url'].strip():
        complete += 1
print(f"Total items: {total}")
print(f"Complete (title + abstract + url): {complete}/{total}")