#!/usr/bin/env python3
# ---- RSS Aggregator Service Entrypoint (Debug Enhanced) ----
import os, re, json, time, socket, asyncio, threading, traceback
from urllib.parse import urlparse
from setup import setup_service_environment
from intel.orchestrator import run_orchestrator


# ---- Redis helpers ----
def parse(u):
    p = urlparse(u or "redis://127.0.0.1:6379")
    return (p.hostname or "127.0.0.1", p.port or 6379)


def guess_service_id():
    """Derive the service ID from environment or container naming."""
    sid = os.getenv("SERVICE_ID")
    if sid:
        print(f"[debug] SERVICE_ID environment variable = {sid}")
        return sid
    hn = os.getenv("HOSTNAME") or socket.gethostname()
    print(f"[debug] HOSTNAME fallback = {hn}")
    m = re.match(r"^[^-]+-([^-]+)-\d+$", hn)
    if m:
        print(f"[debug] Parsed hostname-derived service ID = {m.group(1)}")
        return m.group(1)
    try:
        with open("/proc/1/cpuset") as f:
            cp = f.read().strip()
        m = re.search(r"/[^/]+/([^/]+)/[0-9a-f]+$", cp)
        if m:
            print(f"[debug] Parsed cpuset-derived service ID = {m.group(1)}")
            return m.group(1)
    except Exception:
        pass
    print(f"[debug] Using hostname as service ID = {hn}")
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
            print(f"🚀 Launching RSS Aggregator orchestrator for {svc} ...")
            await run_orchestrator(svc)
        except Exception as e:
            print(f"❌ Orchestrator crashed: {e}")
            traceback.print_exc()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run())


# ---- Entrypoint ----
if __name__ == "__main__":
    svc = guess_service_id()
    print(f"🧠 Initializing {svc} service...")

    # ---- Connect to Redis + fetch Truth document ----
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
    host, port = parse(redis_url)
    print(f"[debug] Connecting to Redis host={host} port={port} ...")
    try:
        s = socket.create_connection((host, port), 2)
        print("[debug] Connected to Redis successfully.")
        truth_raw = get_bulk(s, "truth:doc")
        if not truth_raw:
            print("[debug] truth:doc key not found in Redis.")
        else:
            print(f"[debug] Loaded truth:doc ({len(truth_raw)} bytes)")
        truth = json.loads((truth_raw or b"{}").decode() or "{}")
    except Exception as e:
        print(f"❌ Failed to connect to Redis or load truth:doc: {e}")
        traceback.print_exc()
        exit(1)

    # ---- Find heartbeat endpoint for this service ----
    comps = truth.get("components", {})
    if not comps:
        print("[debug] No 'components' found in truth:doc.")
    else:
        print(f"[debug] Found {len(comps)} components in truth:doc: {list(comps.keys())}")

    this_comp = comps.get(svc)
    if not this_comp:
        print(f"[debug] No component block found for '{svc}' in truth:doc.")
    else:
        aps = this_comp.get("access_points", {})
        print(f"[debug] Found access_points for '{svc}': {json.dumps(aps, indent=2)}")

    pubs = (
        comps.get(svc, {})
             .get("access_points", {})
             .get("publish_to", [])
        or []
    )
    print(f"[debug] publish_to list: {json.dumps(pubs, indent=2)}")

    hb = next((x for x in pubs if x.get("key", "").endswith(":heartbeat")), None)
    if hb:
        print(f"[debug] Heartbeat entry found: {hb}")
    else:
        print(f"[debug] No heartbeat entry found for {svc}")
    assert hb, f"no heartbeat publish_to found for {svc}"

    bus = hb.get("bus", "system-redis")
    ch = hb["key"]
    bus_map = {
        "system-redis": ("127.0.0.1", 6379),
        "market-redis": ("127.0.0.1", 6380),
        "rss-redis": ("127.0.0.1", 6381)
    }
    bh, bp = bus_map.get(bus, (host, port))
    print(f"[debug] Resolved heartbeat bus={bus} host={bh} port={bp} key={ch}")

    ps = s if (bh, bp) == (host, port) else socket.create_connection((bh, bp), 2)
    print(f"[debug] Ready to publish heartbeat to {bus}:{ch}")

    # ---- 1️⃣ Setup working environment ----
    try:
        setup_service_environment(svc)
        print("✅ Environment setup complete.")
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        traceback.print_exc()
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
            payload = json.dumps({"svc": svc, "i": i, "ts": int(time.time())})
            send(ps, "PUBLISH", ch, payload)
            ack = rdline(ps)
            print(f"[debug] Redis publish ack: {ack}")
            print(f"beat {svc} #{i} -> {ch}", flush=True)
            time.sleep(interval)
        except Exception as e:
            print(f"⚠️ Heartbeat error: {e}")
            traceback.print_exc()
            time.sleep(interval)