# ---- Truth → Bootstrap → Heartbeat ----
import os, re, json, time, socket
from urllib.parse import urlparse
from vexy_ai import run  # local import

def parse_redis_url(url: str):
    p = urlparse(url or "redis://system-redis:6379")
    return (p.hostname or "system-redis", p.port or 6379)

def guess_service_id():
    sid = os.getenv("SERVICE_ID")
    if sid: return sid
    hn = os.getenv("HOSTNAME") or socket.gethostname()
    if m := re.match(r"^[^-]+-([^-]+)-\d+$", hn): return m.group(1)
    try:
        with open("/proc/1/cpuset") as f:
            if m := re.search(r"/[^/]+/([^/]+)/[0-9a-f]+$", f.read().strip()):
                return m.group(1)
    except: pass
    return hn

def send(sock,*parts):
    parts_b=[(x if isinstance(x,bytes) else str(x).encode()) for x in parts]
    buf=b"*%d\r\n"%len(parts_b)+b"".join([b"$%d\r\n%s\r\n"%(len(p),p) for p in parts_b])
    sock.sendall(buf)

def recv_line(sock):
    data=b""
    while not data.endswith(b"\r\n"):
        data+=sock.recv(1)
    return data[:-2]

def redis_get(sock,key):
    send(sock,"GET",key)
    if sock.recv(1)!=b"$": return None
    ln=int(recv_line(sock))
    if ln<0: return None
    data=sock.recv(ln+2)
    return data[:-2]

# ---- bootstrap ----
svc = guess_service_id()
host, port = parse_redis_url(os.getenv("REDIS_URL"))

# Load truth document
s = socket.create_connection((host, port), 2)
truth = json.loads((redis_get(s, "truth:doc") or b"{}").decode() or "{}")

# Locate heartbeat endpoint
pubs = truth.get("components", {}).get(svc, {}).get("access_points", {}).get("publish_to", [])
hb = next((x for x in pubs if x.get("key", "").endswith(":heartbeat")), None)
assert hb, f"No heartbeat publish_to found for {svc}"

bus, ch = hb.get("bus", "system-redis"), hb["key"]
bus_map = {"system-redis": ("system-redis", 6379), "market-redis": ("market-redis", 6379)}
bh, bp = bus_map.get(bus, (host, port))
ps = s if (bh, bp) == (host, port) else socket.create_connection((bh, bp), 2)

# ---- run Vexy AI core before heartbeat ----
if __name__ == "__main__":
    print(f"🧠 Starting Vexy AI service [{svc}]")
    run(truth)  # pass truth to Vexy for channel awareness

    interval = float(os.getenv("HB_INTERVAL_SEC", "5"))
    i = 0
    while True:
        i += 1
        send(ps, "PUBLISH", ch, json.dumps({"svc": svc, "i": i, "ts": int(time.time())}))
        recv_line(ps)
        print(f"beat {svc} #{i} -> {ch}", flush=True)
        time.sleep(interval)