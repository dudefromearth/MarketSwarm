import os
import asyncio
import json
from workflow import Workflow

async def heartbeat_task(svc: str, interval: float):
    """Continuously emit heartbeats."""
    i = 0
    while True:
        i += 1
        print(f"beat {svc} #{i} -> {svc}:heartbeat", flush=True)
        await asyncio.sleep(interval)

async def subscription_task(wf: Workflow):
    """Run the blocking subscription loop."""
    print(f"🧩 Subscribed channels: {wf.subscriptions}")
    print("✅ Vexy AI is awaiting input events...")
    await wf.start_async()  # async workflow listener

async def main_async():
    svc = os.getenv("SERVICE_ID", "vexy_ai")
    print(f"🤖 Vexy AI online — initializing workflow for {svc}")

    truth = {}  # (will be passed in by main.py)
    wf = Workflow(truth)
    print(f"Workflow started with subscriptions: {wf.subscriptions}")

    # Run both the workflow and heartbeat concurrently
    hb_interval = float(os.getenv("HB_INTERVAL_SEC", "10"))
    await asyncio.gather(
        subscription_task(wf),
        heartbeat_task(svc, hb_interval),
    )

def run(truth=None):
    """Entry point for main.py — runs the async loop."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("🛑 Vexy AI shutdown requested")