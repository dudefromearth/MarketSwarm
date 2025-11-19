#!/usr/bin/env python3
import os, asyncio, json, redis
from openai import AsyncOpenAI
from datetime import datetime, timezone

# ── Clients (exact your ports) ─────────────────────────────────────
system_r = redis.Redis(host="127.0.0.1", port=6379, db=0, decode_responses=True)
market_r = redis.Redis(host="127.0.0.1", port=6380, db=0, decode_responses=True)
intel_r  = redis.Redis(host="127.0.0.1", port=6381, db=0, decode_responses=True)

# xAI client
client = AsyncOpenAI(
    api_key=os.getenv("XAI_API_KEY"),
    base_url="https://api.x.ai/v1"
)

# Subscribe to both rivers
intel_ps = intel_r.pubsub()
intel_ps.subscribe("vexy:intake")

market_ps = market_r.pubsub()
market_ps.subscribe("sse:chain-feed")

SYSTEM_PROMPT = """
You are MarketSwarm Anchor — the calm, precise, professional broadcast voice.
You see real-time SPX option chains, full Greeks, GEX profiles, volume profile, convexity heatmaps, and fresh enriched markdown intelligence.
Speak only truth. Never hallucinate numbers. Never apologise.
Write 4–8 sharp sentences. End with one forward-looking sentence.
Tone: professional trader who has seen every regime.
"""

async def heartbeat():
    i = 0
    while True:
        system_r.publish("vexy_anchor:heartbeat", json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "i": i}))
        i += 1
        await asyncio.sleep(15)

async def speak():
    print("[vexy_anchor] live — watching vexy:intake + sse:chain-feed]")
    while True:
        # Wait for either river
        if intel_ps.get_message(timeout=30) or market_ps.get_message(timeout=0.1):
            # Grab latest from both (non-blocking)
            latest_chain = market_r.xrange("sse:chain-feed", count=1)
            latest_intel = intel_r.xrange("vexy:intake", count=5)  # last 5 articles

            if not latest_chain:
                await asyncio.sleep(5)
                continue

            user_prompt = f"""
Timestamp: {datetime.now(timezone.utc).isoformat()}
Latest chain snapshot: {json.dumps(latest_chain[-1])}
Latest intelligence (up to 5 articles):
{json.dumps(latest_intel)}
What matters right now? Speak.
"""

            try:
                resp = await client.chat.completions.create(
                    model="grok-4-fast-reasoning",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": user_prompt}
                    ],
                    temperature=0.6,
                    max_tokens=900
                )
                text = resp.choices[0].message.content.strip()

                payload = {
                    "layer": "anchor",
                    "text": text,
                    "ts": datetime.now(timezone.utc).isoformat()
                }
                market_r.publish("vexy:playbyplay", json.dumps(payload))
                print(f"[anchor] spoke — {len(text.split())} words")

            except Exception as e:
                print(f"[anchor] error: {e}")

        await asyncio.sleep(1)

async def main():
    await asyncio.gather(heartbeat(), speak())

if __name__ == "__main__":
    asyncio.run(main())