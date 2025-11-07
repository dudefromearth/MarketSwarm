# services/healer/monitor.py
from __future__ import annotations
import json, logging, os, socket, threading, time
from urllib.parse import urlparse
from notifier import Notifier

# ---- Minimal RESP client (GET/SET/PUBLISH/SUBSCRIBE) ----
class R:
    def __init__(self, host="system-redis", port=6379, timeout=15.0, log=None):
        self.h, self.p, self.t, self.log = host, port, timeout, log
        self.s = socket.create_connection((self.h, self.p), timeout=self.t)
    def _send(self,*parts):
        enc=[(b if isinstance(b,(bytes,bytearray)) else str(b).encode()) for b in parts]
        buf=b"*%d\r\n"%len(enc)+b"".join([b"$%d\r\n%s\r\n"%(len(b),b) for b in enc])
        self.s.sendall(buf)
    def _rdline(self):
        b=bytearray()
        while True:
            ch=self.s.recv(1)
            if not ch: raise ConnectionError("closed")
            b.extend(ch)
            if b.endswith(b"\r\n"): return bytes(b[:-2])
    def _rdbulk(self):
        ln=int(self._rdline())
        if ln==-1: return None
        need=ln+2; data=bytearray()
        while need:
            c=self.s.recv(need)
            if not c: raise ConnectionError("short read")
            data.extend(c); need-=len(c)
        return bytes(data[:-2])
    def _parse(self):
        t=self.s.recv(1)
        if not t: raise ConnectionError("closed")
        if t==b'+': return self._rdline().decode()
        if t==b'-': raise RuntimeError(self._rdline().decode())
        if t==b':': return int(self._rdline())
        if t==b'$': return self._rdbulk()
        if t==b'*': return [self._parse() for _ in range(int(self._rdline()))]
        raise RuntimeError(f"bad reply {t!r}")
    def cmd(self,*parts):
        try: self._send(*parts); return self._parse()
        except Exception:
            if self.log: self.log.warning("redis reconnect %s:%s", self.h, self.p)
            self.s = socket.create_connection((self.h,self.p), timeout=self.t)
            self._send(*parts); return self._parse()
    def get(self,k): v=self.cmd("GET",k); return v if isinstance(v,(bytes,type(None))) else None
    def set(self,k,v): return self.cmd("SET",k,v)
    def pub(self,ch,msg): return self.cmd("PUBLISH",ch,msg)
    def sub(self,*chs):  self._send("SUBSCRIBE",*chs); return self._parse()

# ---- helpers ----

def parse_url(u:str)->tuple[str,int]:
    p=urlparse(u); return (p.hostname or "system-redis", p.port or 6379)


def load_truth(redis_url:str, key:str, log)->dict:
    host,port=parse_url(redis_url); r=R(host,port,log=log); raw=r.get(key)
    if not raw:
        log.warning("truth key %s empty on %s:%s", key, host, port); return {}
    try: return json.loads(raw.decode())
    except Exception as e:
        log.error("truth JSON invalid: %s", e); return {}


def healer_subscriptions(truth:dict)->dict[str,list[str]]:
    """Return {bus_name: [channels...]} from truth.components/services.healer.access_points.subscribe_to."""
    node = (truth.get("services") or {}).get("healer")
    if not node:
        node = (truth.get("components") or {}).get("healer") or {}
    subs=(node.get("access_points") or {}).get("subscribe_to") or []
    buses:dict[str,list[str]]={}
    for it in subs:
        bus=it.get("bus","system-redis"); ch=it.get("key")
        if ch: buses.setdefault(bus,[]).append(ch)
    return buses


def bus_hostport(bus:str)->tuple[str,int]:
    return ("market-redis",6379) if bus=="market-redis" else ("system-redis",6379)


def main():
    # ---- config/env ----
    loglvl = os.getenv("LOG_LEVEL","INFO").upper()
    logging.basicConfig(level=getattr(logging,loglvl,logging.INFO),
                        format="%(asctime)s %(levelname)s healer - %(message)s")
    log = logging.getLogger("healer")

    svc_id = os.getenv("SERVICE_ID","healer")
    truth_url = os.getenv("TRUTH_REDIS_URL", os.getenv("REDIS_URL","redis://system-redis:6379"))
    truth_key = os.getenv("TRUTH_REDIS_KEY","truth:doc")
    default_timeout = float(os.getenv("DEFAULT_TIMEOUT_SEC","30"))
    alert_chan = os.getenv("ALERT_CHANNEL","healer:alerts")
    hb_chan   = os.getenv("HEALER_HEARTBEAT_CHANNEL","healer:heartbeat")
    hb_interval = float(os.getenv("HB_INTERVAL_SEC","10"))

    # ---- load truth & pick channels to subscribe to ----
    truth = load_truth(truth_url, truth_key, log)
    buses = healer_subscriptions(truth)
    thr = (((truth.get("services") or {}).get("healer") or (truth.get("components") or {}).get("healer") or {}).get("threshold") or {})
    timeout_sec = float(thr.get("heartbeat_cadence", default_timeout))

    if not buses:
        log.warning("no healer.subscribe_to endpoints found in truth; nothing to monitor")

    # ---- pub Redis client (alerts + health KV) on system bus ----
    sys_h, sys_p = bus_hostport("system-redis")
    pub = R(sys_h, sys_p, log=log)
    notifier = Notifier(log, alert_chan)

    # ---- subscriber threads per bus ----
    start_ts = time.time()

    # expected services from channel names
    expected_svcs = sorted(set(ch.split(":",1)[0] for chs in buses.values() for ch in chs))

    # per-svc state
    last_seen:dict[str,float|None] = {svc: None for svc in expected_svcs}  # None => not yet seen
    alerted:  dict[str,bool]       = {svc: False for svc in expected_svcs}

    # warmup window per service to avoid false misses right after healer restart
    def warmup_until_for(svc:str) -> float:
        svc_cfg = ((truth.get("services") or {}).get(svc) or (truth.get("components") or {}).get(svc) or {}).get("heartbeat") or {}
        interval = float(svc_cfg.get("interval_sec") or os.getenv("DEFAULT_HB_INTERVAL_SEC","10"))
        warmup = min(timeout_sec, max(2*interval, 0.75*timeout_sec))
        return start_ts + warmup

    warmup_until:dict[str,float] = {svc: warmup_until_for(svc) for svc in expected_svcs}

    stop=False; threads=[]

    def reader(bus:str, host:str, port:int, channels:list[str]):
        nonlocal stop
        while not stop:
            try:
                sub = R(host,port,log=log)
                sub.sub(*channels)  # ack array ignored
                log.info("listening %s %s:%s ch=%s", bus, host, port, ",".join(channels))
                while not stop:
                    msg = sub._parse()
                    if isinstance(msg,list) and (msg[0]==b"message" or msg[0]=="message"):
                        ch = msg[1].decode() if isinstance(msg[1],(bytes,bytearray)) else str(msg[1])
                        svc = ch.split(":",1)[0]
                        last_seen[svc] = time.time()
            except Exception as e:
                log.warning("reader %s reconnect after: %s", bus, e); time.sleep(1.0)

    for bus, chs in buses.items():
        h,p = bus_hostport(bus)
        t = threading.Thread(target=reader, args=(bus,h,p,chs), daemon=True)
        t.start(); threads.append(t)

    # ---- healer's own heartbeat (optional) ----
    def hb():
        i=0
        while True:
            i+=1
            try:
                pub.pub(hb_chan, json.dumps({"svc":svc_id,"i":i,"ts":int(time.time())}))
            except Exception as e:
                log.warning("healer hb publish fail: %s", e)
            time.sleep(hb_interval)
    threading.Thread(target=hb, daemon=True).start()

    # ---- watchdog loop: uses warmup to prevent false misses on restart ----
    log.info("monitoring %d services, timeout=%.1fs, alerts→%s", len(expected_svcs), timeout_sec, alert_chan)
    while True:
        now = time.time()
        for svc in expected_svcs:
            tlast = last_seen[svc]  # float | None
            # Not seen yet: only alert after warmup window
            if tlast is None:
                if now > warmup_until[svc] and not alerted[svc]:
                    ev = {"type":"heartbeat_miss","svc":svc,
                          "late_sec": round(now - warmup_until[svc], 2),
                          "timeout_sec": timeout_sec, "ts": int(now)}
                    pub.pub(alert_chan, json.dumps(ev)); pub.set(f"health:{svc}", json.dumps(ev))
                    notifier.notify(ev)
                    alerted[svc] = True
                continue

            # Seen at least one beat: normal late detection
            if (now - tlast) > timeout_sec:
                if not alerted[svc]:
                    ev = {"type":"heartbeat_miss","svc":svc,
                          "late_sec": round(now - tlast, 2),
                          "timeout_sec": timeout_sec, "ts": int(now)}
                    pub.pub(alert_chan, json.dumps(ev)); pub.set(f"health:{svc}", json.dumps(ev))
                    notifier.notify(ev)
                    alerted[svc] = True
            else:
                if alerted[svc]:
                    ev = {"type":"heartbeat_ok","svc":svc,
                          "age_sec": round(now - tlast, 2),
                          "ts": int(now)}
                    pub.pub(alert_chan, json.dumps(ev)); pub.set(f"health:{svc}", json.dumps(ev))
                    notifier.notify(ev)
                    alerted[svc] = False
        time.sleep(1.0)


if __name__ == "__main__":
    main()
