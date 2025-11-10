#!/usr/bin/env python3
"""
RSS Aggregator Service Entrypoint (Managed + PID + TTL Heartbeats)
==================================================================

Purpose
-------
Runs the RSS Aggregator as a long-lived service with:
- **Single-instance control** via PID file + file lock (flock) to prevent double starts.
- **Friendly process title** (optional) for easy `ps`/`pgrep` discovery.
- **Graceful shutdown** on SIGINT/SIGTERM/SIGHUP/SIGQUIT (stops orchestrator, closes sockets, removes PID).
- **Heartbeat emission** to Redis using:
    1) `SET <key> <payload> EX <ttl>` (self-expiring liveness)
    2) `PUBLISH <key> <payload>` (visibility / logs)
- **Background orchestrator** running inside its own asyncio event loop & thread.

Launch contexts
---------------
- Invoked by the host-native launcher (e.g., `rssagg.sh`) or directly during development.
- When launched by the shell supervisor, this script’s PID file complements (does not replace)
  the supervisor’s PID/PGID files.

Environment Variables
---------------------
- SERVICE_ID           : Service identity; if unset, derived from hostname/container hints.
- REDIS_URL            : Base Redis URL (default: redis://127.0.0.1:6379).
- HB_INTERVAL_SEC      : Heartbeat interval seconds (default: 5).
- HB_TTL_SEC           : TTL for the liveness key (default: 15).
- RSSAGG_PID_FILE      : Path to this process’s pidfile (default: /tmp/rss_agg.main.pid).
- PROC_TITLE           : Process title shown in `ps` (default: "rss_agg:main").

Exit Codes
----------
- 1 : Redis critical failure / truth load failure / setup failure.
- 4 : Another instance detected via pidfile/lock (refuses to start).

Notes
-----
- Uses minimal Redis over raw sockets (RESP) to avoid extra dependencies.
- Requires Unix-like platform for `fcntl.flock`. If unavailable, pidfile still helps,
  but double-start protection is best-effort.
"""

import os
import re
import json
import time
import socket
import asyncio
import threading
import traceback
import signal
import errno
from urllib.parse import urlparse

# Optional: friendlier process name in ps/top via `pip install setproctitle`
try:
    import setproctitle  # type: ignore
except Exception:
    setproctitle = None

# flock (Unix). If unavailable, we still use a pidfile with best-effort semantics.
try:
    import fcntl  # type: ignore
except Exception:
    fcntl = None

# Local imports (service bootstrap + orchestrator)
from setup import setup_service_environment
from intel.orchestrator import run_orchestrator

# ----------------------------- PID / Lock state ------------------------------

_PID_FILE = os.getenv("RSSAGG_PID_FILE", "/tmp/rss_agg.main.pid")
_PROC_TITLE = os.getenv("PROC_TITLE", "rss_agg:main")

_lock_fp = None                 # File handle that holds the flock (if available)
_shutdown = threading.Event()   # Cooperative shutdown signal
_orch_thread = None             # Orchestrator thread
_orch_loop = None               # Orchestrator's event loop (thread-local)
_orch_task = None               # The orchestrator's root coroutine task


# =============================== Utilities ===================================

def set_title() -> None:
    """Set a friendly process title (best-effort)."""
    if setproctitle:
        try:
            setproctitle.setproctitle(_PROC_TITLE)
        except Exception:
            # Non-fatal; process still runs without a custom title.
            pass


def pid_running(pid: int) -> bool:
    """
    Check if a PID is running (and not a zombie). EPERM implies the PID exists
    but we lack permissions, which is still 'running' from our perspective.
    """
    if pid <= 1:  # Guard against nonsense PIDs (1 is init/systemd).
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError as e:
        return e.errno not in (errno.ESRCH,)  # ESRCH = no such process


def acquire_pidfile() -> None:
    """
    Single-instance guard:
    - Opens/creates the pidfile
    - Attempts a non-blocking exclusive lock (if flock available)
    - Refuses to start if the pidfile points to a *live* process
    - Writes our PID atomically (truncate+fsync)
    """
    global _lock_fp

    # Ensure directory exists
    pid_dir = os.path.dirname(_PID_FILE) or "."
    os.makedirs(pid_dir, exist_ok=True)

    _lock_fp = open(_PID_FILE, "a+")
    try:
        if fcntl:
            fcntl.flock(_lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # If fcntl is unavailable, proceed; pidfile still helps (best-effort).
    except (OSError, BlockingIOError):
        # Another instance likely holds the lock. Surface the existing PID if readable.
        try:
            _lock_fp.seek(0)
            existing = _lock_fp.read().strip()
        except Exception:
            existing = "unknown"
        print(f"❌ Another rss_agg instance appears to be running "
              f"(pidfile {_PID_FILE}, pid={existing}).")
        raise SystemExit(4)

    # If the pidfile already contains a live PID, refuse to start.
    try:
        _lock_fp.seek(0)
        content = _lock_fp.read().strip()
        if content:
            try:
                old = int(content)
                if pid_running(old):
                    print(f"❌ Detected live process with pid={old} from {_PID_FILE}; refusing to start.")
                    raise SystemExit(4)
            except ValueError:
                # Non-integer pid recorded; we will overwrite.
                pass
    except Exception:
        pass

    # Truncate & write our PID (durable)
    try:
        _lock_fp.seek(0)
        _lock_fp.truncate()
        _lock_fp.write(str(os.getpid()))
        _lock_fp.flush()
        os.fsync(_lock_fp.fileno())
        print(f"[debug] Wrote PID {os.getpid()} to {_PID_FILE}")
    except Exception as e:
        # Non-fatal; we keep running but double-start protection weakens.
        print(f"⚠️ Failed to write pidfile {_PID_FILE}: {e}")


def release_pidfile() -> None:
    """Release lock (if any) and remove the pidfile on clean exit."""
    try:
        if _lock_fp:
            try:
                _lock_fp.truncate(0)
                _lock_fp.flush()
                os.fsync(_lock_fp.fileno())
            except Exception:
                pass
            try:
                if fcntl:
                    fcntl.flock(_lock_fp.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                _lock_fp.close()
            except Exception:
                pass
        # Attempt to remove the file
        try:
            if os.path.exists(_PID_FILE):
                os.remove(_PID_FILE)
        except Exception:
            pass
    except Exception:
        pass


# ================================ Redis I/O ==================================

def parse(u: str):
    """Parse a redis:// URL, returning (host, port) with safe defaults."""
    p = urlparse(u or "redis://127.0.0.1:6379")
    return (p.hostname or "127.0.0.1", p.port or 6379)


def send(sock: socket.socket, *parts) -> None:
    """
    Send a Redis command via raw RESP protocol.
    Example: send(sock, "SET", "key", "value", "EX", 10)
    """
    enc = [(x if isinstance(x, bytes) else str(x).encode()) for x in parts]
    buf = b"*%d\r\n" % len(enc) + b"".join([b"$%d\r\n%s\r\n" % (len(x), x) for x in enc])
    sock.sendall(buf)


def rdline(sock: socket.socket) -> bytes:
    """
    Read a CRLF-terminated line from the Redis socket.
    Raises ConnectionError if the socket closes.
    """
    b = b""
    while not b.endswith(b"\r\n"):
        chunk = sock.recv(1)
        if not chunk:
            raise ConnectionError("Redis socket closed")
        b += chunk
    return b[:-2]


def get_bulk(sock: socket.socket, key: str):
    """
    Perform a Redis GET and return raw bytes (None if key missing).
    Simplified for bootstrap reads (e.g., truth:doc).
    """
    send(sock, "GET", key)
    assert sock.recv(1) == b"$"  # next token is bulk length
    ln = int(rdline(sock))
    if ln < 0:
        return None
    data = b""
    while len(data) < ln + 2:
        data += sock.recv(ln + 2 - len(data))
    return data[:-2]


# ============================== Identity & Truth ==============================

def guess_service_id() -> str:
    """
    Determine service ID:
    1) SERVICE_ID env
    2) parse container-ish hostname forms
    3) cpuset hints
    4) fallback to hostname
    """
    sid = os.getenv("SERVICE_ID")
    if sid:
        print(f"[debug] SERVICE_ID environment variable = {sid}")
        return sid

    hn = os.getenv("HOSTNAME") or socket.gethostname()
    print(f"[debug] HOSTNAME fallback = {hn}")

    # Common container naming pattern: <prefix>-<svc>-<suffix>
    m = re.match(r"^[^-]+-([^-]+)-\d+$", hn)
    if m:
        print(f"[debug] Parsed hostname-derived service ID = {m.group(1)}")
        return m.group(1)

    # cpuset hint (containers) — best-effort
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


# ========================== Orchestrator threading ===========================

def _orchestrator_thread_fn(svc: str) -> None:
    """
    Thread target:
    - Creates an event loop dedicated to the orchestrator
    - Runs the orchestrator coroutine until stop is requested
    - On shutdown: cancels remaining tasks and closes the loop
    """
    global _orch_loop, _orch_task

    try:
        _orch_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_orch_loop)

        async def _runner():
            try:
                print(f"🚀 Launching RSS Aggregator orchestrator for {svc} ...")
                await run_orchestrator(svc)
            except asyncio.CancelledError:
                print("ℹ️ Orchestrator task cancelled.")
            except Exception as e:
                print(f"❌ Orchestrator crashed: {e}")
                traceback.print_exc()

        _orch_task = _orch_loop.create_task(_runner())
        _orch_loop.run_forever()

    finally:
        # Shutdown path: cancel outstanding tasks and close the loop cleanly.
        try:
            if _orch_task and not _orch_task.done():
                _orch_task.cancel()
                _orch_loop.run_until_complete(asyncio.sleep(0))  # let cancel propagate
        except Exception:
            pass

        # Gather and finish pending tasks (Py 3.10/3.11 compatible)
        try:
            try:
                pending = asyncio.all_tasks()  # 3.11+
            except TypeError:
                pending = asyncio.all_tasks(_orch_loop)  # <=3.10
            for t in pending:
                if not t.done():
                    t.cancel()
            _orch_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass

        try:
            _orch_loop.close()
        except Exception:
            pass


def start_async_orchestrator(svc: str) -> None:
    """Start the orchestrator in a daemon thread with its own event loop."""
    global _orch_thread
    _orch_thread = threading.Thread(target=_orchestrator_thread_fn, args=(svc,), daemon=True)
    _orch_thread.start()


def stop_orchestrator() -> None:
    """
    Signal the orchestrator to stop:
    - Cancel the root task (if alive)
    - Stop the event loop
    - Join the thread with a small timeout
    """
    if _orch_loop:
        try:
            if _orch_task and not _orch_task.done():
                _orch_loop.call_soon_threadsafe(_orch_task.cancel)
            _orch_loop.call_soon_threadsafe(_orch_loop.stop)
        except Exception:
            pass
    if _orch_thread:
        try:
            _orch_thread.join(timeout=5)
        except Exception:
            pass


# ================================= Entrypoint ================================

if __name__ == "__main__":
    # 1) Process identity + single-instance guard
    set_title()
    acquire_pidfile()

    # 2) Service ID resolution
    svc = guess_service_id()
    print(f"🧠 Initializing {svc} service...")

    # 3) Connect to Redis (base bus) and load truth document.
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
    host, port = parse(redis_url)
    print(f"[debug] Connecting to Redis host={host} port={port} ...")
    s = None  # Base Redis connection
    ps = None # Heartbeat bus connection (can reuse base if same host/port)
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
        release_pidfile()
        raise SystemExit(1)

    # 4) Resolve heartbeat destination from truth:doc (publish_to entry ending with :heartbeat)
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

    pubs = (comps.get(svc, {}).get("access_points", {}).get("publish_to", []) or [])
    print(f"[debug] publish_to list: {json.dumps(pubs, indent=2)}")

    hb = next((x for x in pubs if x.get("key", "").endswith(":heartbeat")), None)
    if hb:
        print(f"[debug] Heartbeat entry found: {hb}")
    else:
        print(f"[debug] No heartbeat entry found for {svc}")
    assert hb, f"no heartbeat publish_to found for {svc}"

    # Map bus name -> host/port (host-native defaults)
    bus = hb.get("bus", "system-redis")
    ch = hb["key"]
    bus_map = {
        "system-redis": ("127.0.0.1", 6379),
        "market-redis": ("127.0.0.1", 6380),
        "rss-redis": ("127.0.0.1", 6381),
    }
    bh, bp = bus_map.get(bus, (host, port))
    print(f"[debug] Resolved heartbeat bus={bus} host={bh} port={bp} key={ch}")

    # Connect a dedicated socket for heartbeats (or reuse base if same bus)
    try:
        ps = s if (bh, bp) == (host, port) else socket.create_connection((bh, bp), 2)
        print(f"[debug] Ready to publish heartbeat to {bus}:{ch}")
    except Exception as e:
        print(f"❌ Failed to connect heartbeat socket: {e}")
        traceback.print_exc()
        release_pidfile()
        raise SystemExit(1)

    # 5) Ensure working dirs/schemas are ready (idempotent)
    try:
        setup_service_environment(svc)
        print("✅ Environment setup complete.")
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        traceback.print_exc()
        release_pidfile()
        raise SystemExit(1)

    # 6) Start orchestrator in background thread
    start_async_orchestrator(svc)

    # 7) Heartbeat loop (SET with TTL + PUBLISH)
    interval = float(os.getenv("HB_INTERVAL_SEC", "5"))
    ttl = int(os.getenv("HB_TTL_SEC", "15"))
    i = 0
    print("💓 Heartbeat active...")

    def _shutdown_handler(signum, frame):
        """Trap POSIX signals to initiate graceful shutdown."""
        print(f"🔻 Received signal {signum}; shutting down…")
        _shutdown.set()

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT):
        try:
            signal.signal(sig, _shutdown_handler)
        except Exception:
            # Some environments (threads, restricted runtimes) may not allow this.
            pass

    try:
        while not _shutdown.is_set():
            try:
                i += 1
                payload = json.dumps({"svc": svc, "i": i, "ts": int(time.time())})

                # 1) Liveness key with TTL => healer can detect dead processes without pub/sub.
                send(ps, "SET", ch, payload, "EX", ttl)
                ack1 = rdline(ps)

                # 2) Optional pub-sub publish for observers/logs.
                send(ps, "PUBLISH", ch, payload)
                ack2 = rdline(ps)

                print(f"[debug] Redis acks: SET->{ack1} PUBLISH->{ack2}")
                print(f"beat {svc} #{i} -> {ch}", flush=True)

                # Wait for next beat; wake early if shutdown requested.
                _shutdown.wait(interval)
            except Exception as e:
                # Socket hiccups, transient Redis downtime, etc.
                print(f"⚠️ Heartbeat error: {e}")
                traceback.print_exc()
                _shutdown.wait(interval)
    finally:
        # 8) Cleanup path: stop orchestrator, close sockets, release pidfile.
        print("🧹 Cleaning up…")
        try:
            stop_orchestrator()
        except Exception:
            pass
        try:
            if ps:
                ps.close()
        except Exception:
            pass
        try:
            if s and s is not ps:
                s.close()
        except Exception:
            pass
        release_pidfile()
        print("✅ Shutdown complete.")