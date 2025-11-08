#!/usr/bin/env python3
# ---- RSS Aggregator Service Entrypoint ----
import os, re, json, time, socket, asyncio, threading
from urllib.parse import urlparse
from setup import setup_service_environment
from intel.orchestrator import run_orchestrator


# ---- Redis helpers ----
def parse(u):
    p = urlparse(u or "redis://system-redis:6379")
    return (p.hostname or "system-redis", p.port or 6379)


def guess_service_id():
    """Derive the service ID from environment or container naming."""
    sid = os.getenv("SERVICE_ID")
    if sid:
        return sid
    hn = os.getenv("HOSTNAME") or socket.gethostname()
    m = re.match(r"^[^-]+-([^-]+)-\d+$", hn)
    if m:
        return m.group(1)
    try:
        with open("/proc/1/cpuset") as f:
            cp = f.read().strip()
        m = re.search(r"/[^/]+/([^/]+)/[0-9a-f]+$", cp)
        if m:
            return m.group(1)
    except Exception:
        pass
    return hn


def send(sock, *parts):
    enc = [(x if isinstance(x, bytes) else str(x).encode()) for x in parts]
    buf = b"*%d\r\n" % len(enc) + b"".join(
        [b"$%d\r\n%s\r\n" % (len(x), x) for x in enc]
    )
    sock.sendall(buf)


def rdline(sock):
    b = b""
    while not b.endswith(b"\r\n"):
        b += sock.recv(1)
    return b[:-2]


def get_bulk(sock, key):
    send(sock, "GET", key)
    assert sock.recv(1) == b"$"
    ln = int(rdline(sock))
    if ln < 0:
        return None
    data = b""
    while len(data) < ln + 2:
        data += sock.recv(ln + 2 - len(data))
    return data[:-2]


# ---- Async orchestrator runner ----
def start_async_orchestrator(svc):
    """Run orchestrator in its own event loop (non-blocking)."""
    async def run():
        try:
            print("🚀 Launching RSS Aggregator orchestrator...")
            await run_orchestrator(svc)
        except Exception as e:
            print(f"❌ Orchestrator crashed: {e}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run())


# ---- Entrypoint ----
if __name__ == "__main__":
    svc = guess_service_id()
    print(f"🧠 Initializing {svc} service...")

    # ---- Connect to Redis + fetch Truth document ----
    host, port = parse(os.getenv("REDIS_URL", "redis://system-redis:6379"))
    s = socket.create_connection((host, port), 2)
    truth = json.loads((get_bulk(s, "truth:doc") or b"{}").decode() or "{}")

    # ---- Find heartbeat endpoint for this service ----
    pubs = (
        truth.get("components", {})
        .get(svc, {})
        .get("access_points", {})
        .get("publish_to", [])
        or []
    )
    hb = next((x for x in pubs if x.get("key", "").endswith(":heartbeat")), None)
    assert hb, f"no heartbeat publish_to found for {svc}"

    bus = hb.get("bus", "system-redis")
    ch = hb["key"]
    bh, bp = {
        "system-redis": ("system-redis", 6379),
        "market-redis": ("market-redis", 6379),
    }.get(bus, (host, port))
    ps = s if (bh, bp) == (host, port) else socket.create_connection((bh, bp), 2)

    # ---- 1️⃣ Setup working environment ----
    try:
        setup_service_environment(svc)
        print("✅ Environment setup complete.")
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        exit(1)

    # ---- 2️⃣ Launch orchestrator (in background thread) ----
    orchestrator_thread = threading.Thread(
        target=start_async_orchestrator, args=(svc,), daemon=True
    )
    orchestrator_thread.start()

    # ---- 3️⃣ Heartbeat loop ----
    interval = float(os.getenv("HB_INTERVAL_SEC", "5"))
    i = 0
    print("💓 Heartbeat active...")
    while True:
        try:
            i += 1
            send(ps, "PUBLISH", ch, json.dumps({"svc": svc, "i": i, "ts": int(time.time())}))
            rdline(ps)
            print(f"beat {svc} #{i} -> {ch}", flush=True)
            time.sleep(interval)
        except Exception as e:
            print(f"⚠️ Heartbeat error: {e}")
            time.sleep(interval)