import redis
from collections import Counter
r = redis.Redis(host='localhost', port=6379, decode_responses=True)
uids = r.zrange("rss:index", 0, -1)
bias_words = {'hawkish': 0, 'dovish': 0, 'rate': 0, 'fomc': 0}
for uid in uids:
    item = r.hgetall(f"rss:item:{uid}")
    abstract = item.get('abstract', '').lower()
    for word in bias_words:
        bias_words[word] += abstract.count(word)
print("Bias Word Counts in Abstracts:")
for word, count in bias_words.items():
    print(f"{word}: {count}")