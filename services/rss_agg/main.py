#!/usr/bin/env python3
"""
main.py — Canonical entry for RSS Aggregator.
Now fully synchronous for the pipeline,
while keeping heartbeat async in its own background event loop.
"""

import os
import re
import json
import socket
import asyncio
import traceback
from urllib.parse import urlparse
from datetime import datetime

from setup import setup_service_environment
from intel.orchestrator import run_orchestrator
from heartbeat import start_heartbeat


# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------
def log(component, status, emoji, msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{component}] [{status}] {emoji} {msg}")


# ------------------------------------------------------------
# Resolve service ID
# ------------------------------------------------------------
def guess_service_id():
    sid = os.getenv("SERVICE_ID")
    if sid:
        log("identity", "ok", "🆔", f"SERVICE_ID={sid}")
        return sid

    hn = os.getenv("HOSTNAME") or socket.gethostname()
    m = re.match(r"^[^-]+-([^-]+)-\d+$", hn)
    if m:
        sid = m.group(1)
        log("identity", "ok", "🆔", f"Derived service ID from hostname: {sid}")
        return sid

    log("identity", "ok", "🆔", f"Using hostname as service ID: {hn}")
    return hn


# ------------------------------------------------------------
# Truth Loader (RESP)
# ------------------------------------------------------------
def load_truth():
    redis_url = os.getenv("SYSTEM_REDIS_URL", "redis://127.0.0.1:6379")
    p = urlparse(redis_url)
    host = p.hostname or "127.0.0.1"
    port = p.port or 6379

    log("truth", "info", "🔌", f"Connecting to system-redis at {host}:{port}")

    try:
        s = socket.create_connection((host, port), timeout=2)
        cmd = b"*2\r\n$3\r\nGET\r\n$5\r\ntruth\r\n"
        s.sendall(cmd)

        first = s.recv(1)
        if first != b"$":
            raise RuntimeError("Unexpected RESP response")

        ln_bytes = b""
        while not ln_bytes.endswith(b"\r\n"):
            ln_bytes += s.recv(1)
        ln = int(ln_bytes[:-2])   # strip CRLF

        if ln < 0:
            raise RuntimeError("Truth key missing in Redis")

        data = b""
        remaining = ln + 2
        while remaining > 0:
            chunk = s.recv(remaining)
            data += chunk
            remaining -= len(chunk)

        s.close()
        truth = json.loads(data[:-2].decode())

        log("truth", "ok", "📘", "Loaded truth.json from Redis")
        return truth

    except Exception as e:
        log("truth", "error", "❌", f"Failed to load truth: {e}")
        traceback.print_exc()
        return {}


# ------------------------------------------------------------
# MAIN — now fully synchronous
# ------------------------------------------------------------
def main():
    # 1) Identity
    svc = guess_service_id()

    # 2) Truth
    truth = load_truth()
    if not truth:
        raise SystemExit("❌ Cannot continue without truth")

    comp = truth.get("components", {}).get(svc)
    if not comp:
        log("truth", "error", "❌", f"No component definition for '{svc}'")
        raise SystemExit(1)

    log("truth", "ok", "🔎", f"Component block discovered for {svc}")

    # 3) Heartbeat configuration
    pubs = comp.get("access_points", {}).get("publish_to", [])
    hb = next((x for x in pubs if "heartbeat" in x.get("key", "")), None)
    if not hb:
        log("heartbeat", "error", "❌", "No heartbeat publish_to entry found")
        raise SystemExit(1)

    log("heartbeat", "ok", "❤️",
        f"Heartbeat channel: {hb['key']} on {hb['bus']}")

    # 4) Setup environment
    try:
        log("setup", "info", "⚙️", "Running setup_service_environment()")
        setup_info = setup_service_environment(svc)
        log("setup", "ok", "✅", "Environment ready")
    except Exception as e:
        log("setup", "error", "❌", f"Setup failure: {e}")
        raise SystemExit(1)

    # 5) Start heartbeat in its own asyncio event loop STAYING ASYNC
    log("heartbeat", "info", "💓", "Starting heartbeat loop…")

    def heartbeat_runner():
        asyncio.run(start_heartbeat(svc, truth))

    import threading
    threading.Thread(target=heartbeat_runner, daemon=True).start()

    # 6) Run orchestrator (synchronous)
    log("orchestrator", "info", "🚀", "Starting orchestrator…")
    run_orchestrator(svc, setup_info, truth)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("system", "stop", "🛑", "Service interrupted by user")