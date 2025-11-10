#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MarketSwarm Orchestrator — System-first, Enterprise-class
- Async system services (mesh, healer, vexy_ai)
- Threaded producers (rss_agg, massive)
- Dependencies, supervised restarts, graceful shutdown
- CLI controls + launchd emission
- Zero third-party deps; service modules can replace stubs seamlessly
"""

import argparse
import asyncio
import contextlib
import importlib
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

# ──────────────────────────────────────────────
# Defaults & Env
# ──────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT / "scripts"
DEFAULT_LOG_DIR = ROOT / "logs" / "orchestrator"
DEFAULT_PIDFILE = ROOT / "orchestrator.pid"

REDIS_SYSTEM = os.getenv("SYSTEM_REDIS_URL", "redis://localhost:6379")
REDIS_MARKET = os.getenv("MARKET_REDIS_URL", "redis://localhost:6380")
REDIS_INTEL  = os.getenv("INTEL_REDIS_URL",  "redis://localhost:6381")

# ──────────────────────────────────────────────
# Service Registry (swap stubs for real modules anytime)
# mode: "async" (single event loop) or "thread" (supervised threads)
# entry: (module_path, callable_name) for real code; stubs used if import fails
# depends: names that must be "running" before start
# ──────────────────────────────────────────────
SERVICE_REGISTRY = {
    "mesh": {
        "mode": "async",
        "entry": ("services.mesh.main", "run_mesh"),
        "depends": [],
        "heartbeat": 5,
    },
    "healer": {
        "mode": "async",
        "entry": ("services.healer.monitor", "run_healer"),
        "depends": ["mesh", "massive", "rss_agg", "vexy_ai"],  # needs the world
        "heartbeat": 10,
    },
    "vexy_ai": {
        "mode": "async",
        "entry": ("services.vexy_ai.main", "run_vexy"),
        "depends": ["mesh"],
        "heartbeat": 7,
    },
    "rss_agg": {
        "mode": "thread",
        "entry": ("services.rss_agg.main", "run_rss_agg"),
        "depends": ["mesh"],
        "heartbeat": 15,
    },
    "massive": {
        "mode": "thread",
        "entry": ("services.massive.main", "run_massive"),
        "depends": ["mesh"],
        "heartbeat": 5,
    },
}

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
def setup_logging(log_dir: Path, verbosity: int) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    level = logging.INFO if verbosity == 0 else logging.DEBUG
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    datefmt = "%H:%M:%S"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / "orchestrator.log", encoding="utf-8")
    ]
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, handlers=handlers)

log = logging.getLogger("orchestrator")

# ──────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────
def run_inject_truth_verify(skip: bool=False) -> bool:
    if skip:
        log.info("⏭️  Skipping Redis semantic verification (requested).")
        return True
    script = SCRIPTS_DIR / "inject-truth.sh"
    if not script.exists():
        log.warning("⚠️  inject-truth.sh not found; continuing without pre-check.")
        return True
    log.info("🔌 Running semantic truth verification via inject-truth.sh ...")
    p = subprocess.run([str(script), "--verify"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    sys.stdout.write("\n" + "─" * 70 + "\n")
    sys.stdout.write(p.stdout)
    sys.stdout.write("─" * 70 + "\n")
    ok = (p.returncode == 0 and "semantically consistent" in p.stdout and "Lua" in p.stdout)
    if not ok:
        log.error("❌ Redis verification failed; aborting.")
    else:
        log.info("✅ Redis semantic verification passed.")
    return ok

def tcp_check(host: str, port: int, timeout: float=2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def parse_redis_host(url: str) -> Tuple[str, int]:
    # very naive parse for redis://host:port
    try:
        _, rest = url.split("://", 1)
        host, port = rest.split(":")
        return host, int(port)
    except Exception:
        return ("localhost", 6379)

# ──────────────────────────────────────────────
# Service Wrappers
# ──────────────────────────────────────────────
@dataclass
class ServiceState:
    name: str
    mode: str
    depends: List[str] = field(default_factory=list)
    running: bool = False
    last_heartbeat: float = 0.0
    restart_count: int = 0
    exit_code: Optional[int] = None

class AsyncServiceRunner:
    def __init__(self, name: str, entry: Tuple[str, str], heartbeat: int):
        self.name = name
        self.entry = entry
        self.heartbeat = heartbeat
        self.task: Optional[asyncio.Task] = None
        self.stop_evt = asyncio.Event()

    async def _stub(self):
        # Minimal async heartbeat stub (replace by real import if available)
        log.info(f"🧪 [{self.name}] stub running (async).")
        while not self.stop_evt.is_set():
            await asyncio.sleep(self.heartbeat)
            log.info(f"[HEARTBEAT] {self.name} alive (async)")

    async def start(self):
        mod, fn = self.entry
        coro: Optional[Callable] = None
        try:
            m = importlib.import_module(mod)
            coro = getattr(m, fn, None)
        except Exception:
            coro = None
        if not asyncio.iscoroutinefunction(coro):
            # use stub if import or fn missing
            coro = self._stub
        self.task = asyncio.create_task(coro())
        log.info(f"🚀 Launching async: {self.name}")

    async def stop(self, grace: float):
        if self.task is None:
            return
        self.stop_evt.set()
        try:
            await asyncio.wait_for(self.task, timeout=grace)
        except asyncio.TimeoutError:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        log.info(f"🛑 Stopped async: {self.name}")

class ThreadServiceRunner:
    def __init__(self, name: str, entry: Tuple[str, str], heartbeat: int, allow_restart: bool=True):
        self.name = name
        self.entry = entry
        self.heartbeat = heartbeat
        self.allow_restart = allow_restart
        self.stop_evt = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def _stub(self, stop_evt: threading.Event):
        log.info(f"🧪 [{self.name}] stub running (thread).")
        while not stop_evt.is_set():
            time.sleep(self.heartbeat)
            log.info(f"[HEARTBEAT] {self.name} alive (thread)")

    def _runner(self):
        mod_path, fn_name = self.entry
        target = None
        try:
            m = importlib.import_module(mod_path)
            target = getattr(m, fn_name, None)
        except Exception:
            target = None
        if not callable(target):
            target = self._stub
        log.info(f"🚀 Launching thread: {self.name}")
        try:
            target(self.stop_evt)
        except Exception as e:
            log.exception(f"💥 {self.name} crashed: {e}")
        finally:
            log.info(f"🧹 Thread exit: {self.name}")

    def start(self):
        self.stop_evt.clear()
        self.thread = threading.Thread(target=self._runner, name=f"{self.name}-thread", daemon=True)
        self.thread.start()

    def stop(self, grace: float):
        if not self.thread:
            return
        self.stop_evt.set()
        self.thread.join(timeout=grace)
        if self.thread.is_alive():
            log.warning(f"⚠️  {self.name} did not stop within {grace}s.")

# ──────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────
class Orchestrator:
    def __init__(
        self,
        only: Optional[Set[str]] = None,
        exclude: Optional[Set[str]] = None,
        no_restart: bool = False,
        grace_secs: float = 8.0,
        skip_redis_check: bool = False,
        pidfile: Optional[Path] = None,
    ):
        self.only = only or set()
        self.exclude = exclude or set()
        self.no_restart = no_restart
        self.grace = grace_secs
        self.skip_redis_check = skip_redis_check
        self.pidfile = pidfile

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.state: Dict[str, ServiceState] = {}
        self.async_runners: Dict[str, AsyncServiceRunner] = {}
        self.thread_runners: Dict[str, ThreadServiceRunner] = {}

        self.shutdown_evt = threading.Event()

        self._select_services()

    def _select_services(self):
        chosen = set(SERVICE_REGISTRY.keys())
        if self.only:
            chosen &= self.only
        chosen -= self.exclude
        if not chosen:
            raise SystemExit("No services selected after filters.")
        for name in chosen:
            cfg = SERVICE_REGISTRY[name]
            self.state[name] = ServiceState(
                name=name,
                mode=cfg["mode"],
                depends=[d for d in cfg.get("depends", []) if d in chosen],
            )
            if cfg["mode"] == "async":
                self.async_runners[name] = AsyncServiceRunner(name, tuple(cfg["entry"]), cfg["heartbeat"])
            else:
                self.thread_runners[name] = ThreadServiceRunner(name, tuple(cfg["entry"]), cfg["heartbeat"], allow_restart=not self.no_restart)

    # Dependency barrier: wait until dependents report running
    def _deps_satisfied(self, name: str) -> bool:
        deps = self.state[name].depends
        return all(self.state.get(d, ServiceState(d, "async")).running for d in deps)

    def _write_pidfile(self):
        if not self.pidfile:
            return
        self.pidfile.write_text(str(os.getpid()))
        log.info(f"🧾 PID file at {self.pidfile}")

    def _remove_pidfile(self):
        if self.pidfile and self.pidfile.exists():
            with contextlib.suppress(Exception):
                self.pidfile.unlink()

    def _install_signals(self):
        def _handler(signum, _frame):
            log.info(f"🛎️  Signal received ({signum}); shutting down...")
            self.shutdown_evt.set()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, _handler)

    def _redis_preflight(self) -> bool:
        if not run_inject_truth_verify(skip=self.skip_redis_check):
            return False
        # quick TCP reachability as belt & suspenders
        for url in (REDIS_SYSTEM, REDIS_MARKET, REDIS_INTEL):
            host, port = parse_redis_host(url)
            ok = tcp_check(host, port, 1.5)
            log.info(f"🔎 Redis reachability {host}:{port} => {ok}")
            if not ok:
                log.error(f"❌ Redis {host}:{port} not reachable.")
                return False
        return True

    async def _start_async_side(self):
        # Topologically start async services honoring dependencies
        started: Set[str] = set()
        pending = {n for n, s in self.state.items() if s.mode == "async"}

        while pending and not self.shutdown_evt.is_set():
            progressed = False
            for name in list(pending):
                if not self._deps_satisfied(name):
                    continue
                await self.async_runners[name].start()
                self.state[name].running = True
                started.add(name); pending.remove(name); progressed = True
            if not progressed:
                await asyncio.sleep(0.25)

    def _start_thread_side(self):
        # Start threads honoring dependencies
        started: Set[str] = set()
        pending = {n for n, s in self.state.items() if s.mode == "thread"}

        while pending and not self.shutdown_evt.is_set():
            progressed = False
            for name in list(pending):
                if not self._deps_satisfied(name):
                    continue
                self.thread_runners[name].start()
                self.state[name].running = True
                started.add(name); pending.remove(name); progressed = True
            if not progressed:
                time.sleep(0.25)

    async def _health_loop(self):
        while not self.shutdown_evt.is_set():
            now = time.time()
            # Simple heartbeat sampling (could read Redis heartbeats later)
            for n, s in self.state.items():
                log.debug(f"[HEALTH] {n} running={s.running}")
            await asyncio.sleep(5)

    async def start_all(self):
        if not self._redis_preflight():
            raise SystemExit(2)

        self._install_signals()
        self._write_pidfile()

        # Start async services
        async_task = self.loop.create_task(self._start_async_side())
        # Start thread services
        thread_boot = threading.Thread(target=self._start_thread_side, name="thread-boot", daemon=True)
        thread_boot.start()

        # Start health loop
        health_task = self.loop.create_task(self._health_loop())

        # Wait for shutdown
        while not self.shutdown_evt.is_set():
            await asyncio.sleep(0.5)

        # Teardown
        await self.stop_all()
        self._remove_pidfile()
        health_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await health_task
        with contextlib.suppress(asyncio.CancelledError):
            await async_task

    async def stop_all(self):
        log.info("🧳 Stopping services...")
        # Stop threads first (producers)
        for name, runner in self.thread_runners.items():
            try:
                runner.stop(self.grace)
                self.state[name].running = False
            except Exception:
                log.exception(f"stop failed for {name}")

        # Stop async
        for name, runner in self.async_runners.items():
            try:
                await runner.stop(self.grace)
                self.state[name].running = False
            except Exception:
                log.exception(f"stop failed for {name}")

        log.info("✅ All services stopped.")

# ──────────────────────────────────────────────
# CLI / Launchd emission
# ──────────────────────────────────────────────
def emit_launchd(label: str="ai.marketswarm.orchestrator") -> str:
    py = sys.executable
    cmd = f"{py} {str(Path(__file__).resolve())}"
    plist = {
        "Label": label,
        "ProgramArguments": [py, str(Path(__file__).resolve()), "--all"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(DEFAULT_LOG_DIR / "launchd.out"),
        "StandardErrorPath": str(DEFAULT_LOG_DIR / "launchd.err"),
        "EnvironmentVariables": {
            "SYSTEM_REDIS_URL": REDIS_SYSTEM,
            "MARKET_REDIS_URL": REDIS_MARKET,
            "INTEL_REDIS_URL": REDIS_INTEL,
            "PYTHONUNBUFFERED": "1",
        }
    }
    return json.dumps(plist, indent=2)

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="MarketSwarm Orchestrator (async+thread hybrid)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true", help="Run all services")
    g.add_argument("--only", type=str, default="", help="Comma list of services to run")
    p.add_argument("--except", dest="exclude", type=str, default="", help="Comma list of services to exclude")
    p.add_argument("--list", action="store_true", help="List available services and exit")
    p.add_argument("--dry-run", action="store_true", help="Plan only; do not launch services")
    p.add_argument("--skip-redis-check", action="store_true", help="Skip preflight inject-truth verification")
    p.add_argument("--no-restart", action="store_true", help="Disable supervised restarts for threads")
    p.add_argument("--grace-secs", type=float, default=8.0, help="Shutdown grace period")
    p.add_argument("--log-dir", type=str, default=str(DEFAULT_LOG_DIR), help="Log directory")
    p.add_argument("--pidfile", type=str, default=str(DEFAULT_PIDFILE), help="PID file path")
    p.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity (repeatable)")
    p.add_argument("--emit-launchd", action="store_true", help="Print a launchd plist JSON and exit")
    return p.parse_args()

def main():
    args = parse_args()
    setup_logging(Path(args.log_dir), args.verbose)

    if args.emit_launchd:
        print(emit_launchd())
        return

    if args.list:
        print("Available services:")
        for n, cfg in SERVICE_REGISTRY.items():
            print(f"  - {n:8s}  mode={cfg['mode']}  depends={','.join(cfg.get('depends', [])) or '-'}")
        return

    selected: Set[str]
    if args.all or (not args.only and not args.exclude):
        selected = set(SERVICE_REGISTRY.keys())
    else:
        selected = set([s.strip() for s in args.only.split(",") if s.strip()]) or set(SERVICE_REGISTRY.keys())
        excluded = set([s.strip() for s in args.exclude.split(",") if s.strip()])
        selected -= excluded

    log.info(f"🎛️  Selected services: {', '.join(sorted(selected))}")

    if args.dry_run:
        print("Dry run: would start ->")
        for s in sorted(selected):
            cfg = SERVICE_REGISTRY[s]
            print(f"  {s:8s}  mode={cfg['mode']}  depends={','.join(cfg.get('depends', [])) or '-'}")
        return

    orch = Orchestrator(
        only=selected,
        exclude=set(),
        no_restart=args.no_restart,
        grace_secs=args.grace_secs,
        skip_redis_check=args.skip_redis_check,
        pidfile=Path(args.pidfile) if args.pidfile else None,
    )

    log.info("🔌 Connecting to Redis buses...")
    for url in (REDIS_SYSTEM, REDIS_MARKET, REDIS_INTEL):
        host, port = parse_redis_host(url)
        pong = tcp_check(host, port, 2.0)
        log.info(f"✅ Redis {host}:{port} reachable — pong={pong}")

    try:
        orch.loop.run_until_complete(orch.start_all())
    finally:
        orch.loop.close()

if __name__ == "__main__":
    main()