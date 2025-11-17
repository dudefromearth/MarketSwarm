#!/usr/bin/env python3
import asyncio
import time
import redis.asyncio as redis
from datetime import datetime
from playwright.async_api import async_playwright


def log(comp, status, emoji, msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{comp}] [{status}] {emoji} {msg}")


async def browser_fetch(url: str):
    """Full browser GET with JS, scrolling, and delay."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            resp = await page.goto(url, timeout=20000)
            if not resp or resp.status >= 400:
                log("article_raw", "warn", "⚠️", f"Browser HTTP {resp.status if resp else '??'} for {url}")
                await browser.close()
                return ""

            await page.wait_for_load_state("networkidle")

            await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            await page.wait_for_timeout(800)

            html = await page.content()
            await browser.close()
            return html

    except Exception as e:
        log("article_raw", "error", "🔥", f"Browser fetch failed: {e}")
        return ""


async def fetch_and_store_article(uid, url, title, category, r_intel):

    raw_key = f"rss:article_raw:{uid}"
    enriched_key = f"rss:article:{uid}"

    if await r_intel.exists(enriched_key):
        return
    if await r_intel.exists(raw_key):
        return

    log("article_raw", "info", "🌐", f"Browser fetch → {url}")

    html = await browser_fetch(url)
    if not html or len(html) < 500:
        log("article_raw", "warn", "⚠️", f"No usable HTML for {uid[:8]}")
        return

    await r_intel.hset(raw_key, mapping={
        "uid": uid,
        "url": url,
        "title": title,
        "category": category,
        "raw_html": html,
        "fetched_ts": time.time()
    })

    await r_intel.zadd("rss:article_raw:index", {uid: time.time()})

    log("article_raw", "ok", "📦", f"Stored raw article {uid[:8]}")