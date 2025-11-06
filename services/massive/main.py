# ---- Tiny Truth→Heartbeat + Chain 0DTE (hostname-based SERVICE_ID) ----
import os, re, json, time, socket
from urllib.parse import urlparse
from chain_0dte import run_chain0dte  # New: for options chain

def parse(u):
    p = urlparse(u or "redis://system-redis:6379")
    return (p.hostname or "system-redis", p.port or 6379)

def guess_service_id():
    # 1) explicit override wins
    sid = os.getenv("SERVICE_ID")
    if sid: return sid
    # 2) try compose-style names: project-service-1  → service
    hn = os.getenv("HOSTNAME") or socket.gethostname()
    m = re.match(r"^[^-]+-([^-]+)-\d+$", hn)
    if m: return m.group(1)
    # 3) try cgroup hint: .../project/service/abc123
    try:
        with open("/proc/1/cpuset") as f:
            cp = f.read().strip()
        m = re.search(r"/[^/]+/([^/]+)/[0-9a-f]+$", cp)
        if m: return m.group(1)
    except Exception:
        pass
    # 4) last resort: raw hostname
    return hn

svc = guess_service_id()
host, port = parse(os.getenv("REDIS_URL","redis://system-redis:6379"))

def send(sock,*parts):
    enc=[(x if isinstance(x,bytes) else str(x).encode()) for x in parts]
    buf=b"*%d\r\n"%len(enc)+b"".join([b"$%d\r\n%s\r\n"%(len(x),x) for x in enc])
    sock.sendall(buf)

def rdline(sock):
    b=b""
    while not b.endswith(b"\r\n"): b+=sock.recv(1)
    return b[:-2]

def get_bulk(sock,key):
    send(sock,"GET",key); assert sock.recv(1)==b"$"
    ln=int(rdline(sock));
    if ln<0: return None
    data=b""
    while len(data)<ln+2: data+=sock.recv(ln+2-len(data))
    return data[:-2]

# 1) load truth
s=socket.create_connection((host,port),2)
truth=json.loads((get_bulk(s,"truth:doc") or b"{}").decode() or "{}")

# 2) find this service's heartbeat endpoint from truth.components.<svc>.access_points.publish_to
pubs=(truth.get("components",{}).get(svc,{}).get("access_points",{}).get("publish_to",[]) or [])
hb=next((x for x in pubs if x.get("key","").endswith(":heartbeat")), None)
assert hb, f"no heartbeat publish_to found for {svc}"
bus=hb.get("bus","system-redis"); ch=hb["key"]
bh,bp={"system-redis":("system-redis",6379),"market-redis":("market-redis",6379)}.get(bus,(host,port))
ps = s if (bh,bp)==(host,port) else socket.create_connection((bh,bp),2)

# New: Find chain publish channel (sse:chain-feed) and spot channel
chain_pub = next((x for x in pubs if x.get("key") == "sse:chain-feed"), None)
spot_pub = next((x for x in pubs if x.get("key") == "massive:spot"), None)
chain_ch = chain_pub["key"] if chain_pub else None
spot_bus = spot_pub.get("bus", "system-redis") if spot_pub else bus
spot_ch = spot_pub["key"] if spot_pub else None
spot_sock = ps  # Reuse for now; extend if needed

# Beats (heartbeat every 5s)
hb_interval = float(os.getenv("HB_INTERVAL_SEC", "5"))
# Chain every 30s (configurable)
chain_interval = float(os.getenv("CHAIN_INTERVAL_SEC", "30"))
chain_counter = 0
i = 0
while True:
    i += 1
    send(ps, "PUBLISH", ch, json.dumps({"svc": svc, "i": i, "ts": int(time.time())}))
    rdline(ps)  # drop reply
    print(f"beat {svc} #{i} -> {ch}", flush=True)

    # New: Run chain fetch every chain_interval
    chain_counter += hb_interval
    if chain_counter >= chain_interval and chain_ch:
        try:
            run_chain0dte(ps, chain_ch, underlying=os.getenv("UNDERLYING", "SPX"))
            # Also pub spot separately if channel exists
            if spot_ch and 'spot' in locals():
                spot_data = {"underlying": os.getenv("UNDERLYING", "SPX"), "spot": spot, "ts": int(time.time())}
                send(spot_sock, "PUBLISH", spot_ch, json.dumps(spot_data))
                print(f"Published spot {spot} -> {spot_ch}")
        except Exception as e:
            print(f"Chain/spot pub error: {e}")
        chain_counter = 0

    time.sleep(hb_interval)
# ---- end ----