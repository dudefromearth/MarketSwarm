# services/sentinel/guard.py
from __future__ import annotations
import json, os, socket, time
from urllib.parse import urlparse

class R:
    def __init__(self, host, port, timeout=3.0):
        self.h, self.p, self.t = host, port, timeout
        self.s = socket.create_connection((host, port), timeout=timeout)
        # Keep same timeout for all ops; callers can adjust with set_timeout()
    def set_timeout(self, secs: float | None):
        self.s.settimeout(secs)
    def _send(self,*parts):
        enc=[(b if isinstance(b,(bytes,bytearray)) else str(b).encode()) for b in parts]
        buf=b"*%d\r\n"%len(enc)+b"".join([b"$%d\r\n%s\r\n"%(len(b),b) for b in enc]); self.s.sendall(buf)
    def _rdline(self):
        b=bytearray()
        while True:
            ch=self.s.recv(1)
            if not ch: raise ConnectionError("closed")
            b.extend(ch)
            if b.endswith(b"\r\n"): return bytes(b[:-2])
    def _rdbulk(self):
        n=int(self._rdline())
        if n==-1: return None
        data=bytearray(); need=n+2
        while need:
            c=self.s.recv(need)
            if not c: raise ConnectionError("short read")
            data.extend(c); need-=len(c)
        return bytes(data[:-2])
    def _parse(self):
        t=self.s.recv(1)  # may raise socket.timeout when idle — caller handles
        if not t: raise ConnectionError("closed")
        if t==b'+': return self._rdline().decode()
        if t==b'-': raise RuntimeError(self._rdline().decode())
        if t==b':': return int(self._rdline())
        if t==b'$': return self._rdbulk()
        if t==b'*':
            n=int(self._rdline()); return [self._parse() for _ in range(n)]
        raise RuntimeError("bad reply")
    def cmd(self,*parts):
        try: self._send(*parts); return self._parse()
        except (ConnectionError, OSError, RuntimeError, socket.timeout):
            # one reconnect try per command
            self.s = socket.create_connection((self.h,self.p), timeout=self.t)
            self._send(*parts); return self._parse()
    def get(self,k): v=self.cmd("GET",k); return v if isinstance(v,(bytes,type(None))) else None
    def pub(self,ch,msg): return self.cmd("PUBLISH",ch,msg)
    def sub(self,*chs):  self._send("SUBSCRIBE",*chs); return self._parse()

def parse(u): p=urlparse(u); return (p.hostname or "system-redis", p.port or 6379)

def main():
    truth_url = os.getenv("TRUTH_REDIS_URL","redis://system-redis:6379")
    truth_key = os.getenv("TRUTH_REDIS_KEY","truth:doc")
    host,port = parse(truth_url)

    r = R(host,port,timeout=3.0)
    raw = r.get(truth_key) or b"{}"
    truth = json.loads(raw.decode())

    healer = (truth.get("services") or truth.get("components") or {}).get("healer", {})
    hb = (healer.get("heartbeat") or {})
    hb_chan = hb.get("channel","healer:heartbeat")
    cadence = float(hb.get("interval_sec", 10))
    timeout = float(os.getenv("SENTINEL_TIMEOUT_SEC", max(30, 3*cadence)))

    pubs = (healer.get("access_points",{}).get("publish_to") or [])
    alert_chan = next((p.get("key") for p in pubs if (p.get("key","").endswith(":alerts"))), "healer:alerts")

    # subscriber socket with short read timeout so we can check lateness regularly
    sub = R(host,port,timeout=3.0)
    sub.sub(hb_chan)      # ack
    sub.set_timeout(1.0)  # 1s: time out -> just means “no message yet”

    last = time.time()
    missed = False

    while True:
        now = time.time()
        try:
            msg = sub._parse()
            if isinstance(msg,list) and (msg[0]==b"message" or msg[0]=="message"):
                last = now
                if missed:
                    r.pub(alert_chan, json.dumps({"type":"healer_ok","svc":"healer","ts":int(now)}))
                    missed = False
        except socket.timeout:
            # idle — no frame this second; proceed to lateness check
            pass
        except Exception:
            # reconnect & resubscribe if disconnected or parse error
            time.sleep(0.5)
            sub = R(host,port,timeout=3.0)
            sub.sub(hb_chan)
            sub.set_timeout(1.0)

        # lateness check (runs ~1/s)
        now = time.time()
        if (now - last) > timeout and not missed:
            payload = json.dumps({"type":"healer_miss","svc":"healer",
                                  "late_sec":round(now-last,2),"timeout_sec":timeout,"ts":int(now)})
            r.pub(alert_chan, payload)
            missed = True

        time.sleep(0.2)

if __name__ == "__main__":
    main()