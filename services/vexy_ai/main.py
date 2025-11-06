# ---- Tiny Truth→Heartbeat (hostname-based SERVICE_ID) ----
import os, re, json, time, socket
from urllib.parse import urlparse

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

# beats
interval=float(os.getenv("HB_INTERVAL_SEC","5"))
i=0
while True:
    i+=1
    send(ps,"PUBLISH",ch,json.dumps({"svc":svc,"i":i,"ts":int(time.time())}))
    rdline(ps)  # drop integer reply
    print(f"beat {svc} #{i} -> {ch}", flush=True)
    time.sleep(interval)
# ---- end ----