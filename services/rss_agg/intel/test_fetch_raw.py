#!/usr/bin/env python3
import asyncio
import redis.asyncio as redis
from article_fetcher import fetch_and_store_article

TEST_UID = "test1234abcd0000"
TEST_URL = "https://www.bbc.com/news/world-us-canada-68040658"  # choose any real article
TEST_TITLE = "Test Article Fetch"
TEST_CATEGORY = "testing"


async def main():
    r = redis.Redis(host="127.0.0.1", port=6381, decode_responses=True)

    print("\n=== TEST: RAW ARTICLE FETCH ===")

    # 1. Cleanup any previous test key
    await r.delete(f"rss:article_raw:{TEST_UID}")

    print(f"Fetching: {TEST_URL}")
    await fetch_and_store_article(
        uid=TEST_UID,
        url=TEST_URL,
        title=TEST_TITLE,
        category=TEST_CATEGORY,
        r_intel=r
    )

    print("\n=== REDIS RESULT ===")
    data = await r.hgetall(f"rss:article_raw:{TEST_UID}")

    if not data:
        print("❌ FAILED — no key stored")
        return

    print("✔ Key found:")
    for k, v in data.items():
        print(f"   {k}: {v[:80]}")

    if "raw_html" in data and len(data["raw_html"]) > 200:
        print("\n✔ HTML content looks valid (length OK)")
    else:
        print("\n❌ HTML content missing or too small")


if __name__ == "__main__":
    asyncio.run(main())