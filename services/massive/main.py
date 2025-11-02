# services/massive/main.py
from __future__ import annotations
import json, logging, os, signal, sys, time, socket
from urllib import request, error as urlerror

import requests
from contextlib import closing
import websocket  # already imported

# ---------------- logging ----------------
def setup_logging() -> logging.Logger:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    return logging.getLogger("massive")

# ---------------- graceful stop ----------------
_stop = False
def _handle_signal(signum, frame):
    global _stop
    _stop = True

# ---------------- network probe (already working) ----------------
def net_probe(log: logging.Logger) -> bool:
    timeout = float(os.getenv("NET_TIMEOUT_SEC", "6"))
    host    = os.getenv("NET_HOST", "example.com")
    url     = os.getenv("NET_URL",  "https://example.com")

    try:
        with socket.create_connection(("1.1.1.1", 80), timeout=timeout):
            pass
        log.info("NET: tcp egress OK (1.1.1.1:80)")
    except Exception as e:
        log.error("NET: tcp egress FAIL: %s", e)
        return False

    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        log.info("NET: dns OK (%s)", host)
    except Exception as e:
        log.error("NET: dns FAIL for %s: %s", host, e)
        return False

    try:
        req = request.Request(url, headers={"User-Agent": "MarketSwarm/1.0 (+netprobe)"})
        with request.urlopen(req, timeout=timeout) as r:
            log.info("NET: https OK (%s) status=%s", url, r.status)
    except urlerror.HTTPError as e:
        log.warning("NET: https reachable but HTTP error: %s %s", e.code, e.reason)
        return True
    except Exception as e:
        log.error("NET: https FAIL for %s: %s", url, e)
        return False

    return True

# ---------------- Polygon: REST probe ----------------
def rest_probe(api_key: str, timeout: float, log: logging.Logger) -> bool:
    """
    Minimal REST sanity: call v3 reference tickers (limit=1).
    Returns True if 2xx, logs status & result length.
    """
    url = "https://api.polygon.io/v3/reference/tickers"
    params = {"apiKey": api_key, "limit": 1}
    headers = {"User-Agent": "MarketSwarm/1.0 (+polygon-rest)"}
    try:
        log.info("POLY REST: GET %s %s", url, params)
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        d = r.json()
        log.info("POLY REST: status=%s results_len=%s", d.get("status"), len(d.get("results", [])))
        return True
    except requests.RequestException as e:
        log.error("POLY REST: FAIL %s", e)
        return False

# ---------------- Polygon: WebSocket probe ----------------
def ws_probe(api_key: str, timeout: float, log: logging.Logger) -> bool:
    """
    Connect to Polygon WS, auth, optional subscribe, read a few frames, then close.
    """
    channel   = os.getenv("POLYGON_WS_CHANNEL", "stocks")      # stocks|crypto|forex|indices
    subscribe = os.getenv("POLYGON_SUBSCRIBE", "")             # e.g., "T.AAPL"
    n_frames  = int(os.getenv("POLYGON_WS_READ_FRAMES", "2"))
    ws_url    = f"wss://socket.polygon.io/{channel}"

    log.info("POLY WS: connect %s", ws_url)
    try:
        with closing(websocket.create_connection(
            ws_url,
            timeout=timeout,
            header=["User-Agent: MarketSwarm/1.0 (+polygon-ws)"],
        )) as ws:
            ws.send(json.dumps({"action": "auth", "params": api_key}))
            log.info("POLY WS: sent auth")

            if subscribe:
                ws.send(json.dumps({"action": "subscribe", "params": subscribe}))
                log.info("POLY WS: subscribe %s", subscribe)

            ws.settimeout(timeout)
            for i in range(max(0, n_frames)):
                msg = ws.recv()
                short = (msg[:300] + "…") if isinstance(msg, str) and len(msg) > 300 else msg
                log.info("POLY WS: recv[%d]=%s", i, short)

        log.info("POLY WS: closed")
        return True

    except websocket.WebSocketTimeoutException as e:
        log.error("POLY WS: timeout %s", e)
        return False
    except Exception as e:
        log.error("POLY WS: FAIL %s", e)
        return False

# ---------------- heartbeat ----------------
def heartbeat(interval: float, label: str, count: int | None, log: logging.Logger) -> None:
    i = 0
    while not _stop and (count is None or i < count):
        i += 1
        log.info("heartbeat %s #%d", label, i)
        remaining = float(interval)
        while remaining > 0 and not _stop:
            step = 0.2 if remaining >= 0.2 else remaining
            time.sleep(step)
            remaining -= step
    log.info("heartbeat stopped")

# ---------------- main ----------------
def main() -> int:
    log = setup_logging()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT,  _handle_signal)

    # Heartbeat knobs
    interval   = float(os.getenv("HB_INTERVAL_SEC", "5"))
    label      = os.getenv("HB_LABEL", "massive")
    hb_count_s = os.getenv("HB_COUNT", "")
    count      = None if hb_count_s in ("", "0") else max(1, int(hb_count_s))

    # Probes toggles & settings
    run_net   = os.getenv("NET_PROBE_ON_START", "1") != "0"
    strict    = os.getenv("NET_PROBE_STRICT", "0") == "1"
    timeout   = float(os.getenv("POLYGON_TIMEOUT_SEC", "6"))
    do_rest   = os.getenv("POLYGON_TEST_REST", "1") != "0"
    do_ws     = os.getenv("POLYGON_TEST_WS",   "1") != "0"
    api_key   = os.getenv("POLYGON_API_KEY", "")

    # Run probes
    if run_net:
        ok = net_probe(log)
        if not ok and strict:
            return 10
    if do_rest:
        if not api_key:
            log.error("POLY REST: missing POLYGON_API_KEY")
        else:
            rest_probe(api_key, timeout, log)
    if do_ws:
        if not api_key:
            log.error("POLY WS: missing POLYGON_API_KEY")
        else:
            ws_probe(api_key, timeout, log)

    log.info("starting heartbeat: interval=%ss label=%s count=%s",
             interval, label, ("∞" if count is None else count))
    heartbeat(interval, label, count, log)
    return 0

if __name__ == "__main__":
    sys.exit(main())