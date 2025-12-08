#!/usr/bin/env python3
"""
orchestrator.py — Massive orchestrator

Responsibilities:
- For a given configuration, run the Massive scheduler loop:
    * fast lane (typically 0DTE) with small interval
    * rest lane (1–4DTE or more) with larger interval
    * limit max inflight cycles
- For each cycle, launch massive_chain_loader.py once per symbol,
  either sequentially or via threads depending on workflow.threading_enabled.
- Stream child process output back through the main logger.

Structure:

  run_chain_loader_for_symbol(cfg, symbol, num_expirations)
      → runs one massive_chain_loader subprocess

  run_cycle(cfg, log, stop_flag, num_expirations, label)
      → runs one logical "cycle" across all symbols

  run_orchestrator(cfg, log, stop_flag)
      → scheduler loop (0DTE vs rest lanes, max inflight)

  async run(config)
      → async entrypoint used by main.py
         - runs run_orchestrator() in a background thread
         - cooperates with asyncio cancellation
"""

from __future__ import annotations

import asyncio
import subprocess
import threading
import time
from typing import Any, Callable, Dict, Optional


# ------------------------------------------------------------
# Worker: run chain loader for ONE symbol
# ------------------------------------------------------------

def run_chain_loader_for_symbol(cfg: Dict[str, Any], symbol: str, num_expirations: int) -> None:
    """
    Launches massive_chain_loader.py for exactly one symbol.

    Parameters
    ----------
    cfg : dict
        Global Massive configuration from setup_environment()/setup().
        Expected keys:
          - "CHAIN_LOADER": path to massive_chain_loader.py
          - "PYTHON":       interpreter path
          - "workflow":     workflow config block
          - "redis_market_url": Redis URL for market-redis
    symbol : str
        Ticker symbol (e.g., "I:SPX", "SPY", "QQQ").
    num_expirations : int
        How many expirations to request from the chain loader.
    """

    log = cfg["log"]

    # Path to massive_chain_loader.py and Python interpreter
    script_path = cfg["CHAIN_LOADER"]
    py = cfg["PYTHON"]

    wf = cfg["workflow"]

    # Per-symbol strike ranges
    strike_ranges = wf.get("strike_ranges", {}) or {}
    strike_range = strike_ranges.get(symbol, wf.get("strike_range", 100))

    # Number of expirations for this run
    expirations = num_expirations

    # Strict inequality mode:
    #   prefer use_strict_gt_lt, fall back to legacy use_strict
    strict_flag = wf.get("use_strict_gt_lt", wf.get("use_strict", False))
    strict_mode = "true" if strict_flag else "false"

    # Redis URL (API key is taken from env inside massive_chain_loader)
    redis_url = cfg["redis_market_url"]

    # Debug flags
    debug_rest = cfg.get("debug_rest", False)
    debug_threads = cfg.get("debug_threads", False)

    # Build command — matches massive_chain_loader.py CLI
    # NOTE: we no longer pass --api-key; MASSIVE_API_KEY env is used instead.
    cmd = [
        py,
        script_path,
        "--symbols", symbol,
        "--strike-range", str(strike_range),
        "--strict", strict_mode,
        "--expirations", str(expirations),
        "--redis-url", redis_url,
    ]

    if debug_rest:
        cmd.append("--debug-rest")

    # ---- Logging ----
    log(
        "orchestrator",
        "➡️",
        f"Starting chain loader for {symbol} "
        f"(strike ±{strike_range}, exp={expirations})",
    )
    if debug_threads:
        log("orchestrator", "🧩", f"Cmd: {' '.join(cmd)}")

    # ---- Run subprocess ----
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Stream output live
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                log(symbol, "📤", line)

        proc.wait()

        log(
            "orchestrator",
            "✅",
            f"{symbol} chain load done (exit={proc.returncode})",
        )

    except Exception as e:
        log(
            "orchestrator",
            "❌",
            f"Chain loader failed for {symbol}: {e}",
        )


# ------------------------------------------------------------
# Single "cycle": run loaders for all symbols once
# ------------------------------------------------------------

def run_cycle(
    cfg: Dict[str, Any],
    log: Callable[[str, str, str], None],
    stop_flag: Callable[[], bool],
    num_expirations: Optional[int] = None,
    label: Optional[str] = None,
) -> None:
    """
    Run one orchestrator "cycle":

    - For each symbol in workflow.symbols, launch massive_chain_loader.py
      with the requested number of expirations.
    - Either in parallel (one thread per symbol) or sequentially,
      depending on workflow.threading_enabled.
    - Wait for all loaders to finish.
    - Return (no internal sleeping).
    """

    # Expose main logger to workers
    cfg["log"] = log

    wf = cfg["workflow"]

    symbols = wf.get("symbols", ["I:SPX", "I:NDX", "SPY", "QQQ"])
    threading_enabled = wf.get("threading_enabled", True)

    if num_expirations is None:
        num_expirations = wf.get("num_expirations", 5)

    label = label or f"{num_expirations}exp"

    mode = "threads" if threading_enabled else "sequential"
    log(
        "orchestrator",
        "🌀",
        f"Running {label} cycle with {len(symbols)} symbols "
        f"(exp={num_expirations}, mode={mode})",
    )

    threads: list[threading.Thread] = []

    if threading_enabled:
        # Start one thread per symbol
        for sym in symbols:
            if stop_flag():
                break

            t = threading.Thread(
                target=run_chain_loader_for_symbol,
                args=(cfg, sym, num_expirations),
                daemon=True,
            )
            threads.append(t)
            t.start()
            # Small stagger to avoid bursty API calls
            time.sleep(0.1)

        # Wait for all loaders to finish
        for t in threads:
            t.join()

    else:
        # Sequential mode (useful for debugging)
        for sym in symbols:
            if stop_flag():
                break
            run_chain_loader_for_symbol(cfg, sym, num_expirations)

    log("orchestrator", "✅", f"{label} cycle complete")


# ------------------------------------------------------------
# Scheduler: 0DTE vs rest lanes, with max inflight
# ------------------------------------------------------------

def run_orchestrator(
    cfg: Dict[str, Any],
    log: Callable[[str, str, str], None],
    stop_flag: Callable[[], bool],
) -> None:
    """
    Full Massive scheduler loop.

    Uses cfg["scheduler"] + cfg["workflow"] to:
      - schedule "fast" lane (typically 0DTE) cycles
      - schedule "rest" lane (1–4DTE) cycles
      - respect max inflight worker cycles
      - stop cleanly when stop_flag() becomes True

    This replaces the scheduling loop that used to live in main.py.
    """

    # Expose main logger to workers
    cfg["log"] = log

    scheduler = cfg.get("scheduler", {})
    wf = cfg["workflow"]

    # Trust scheduler values (already built from Truth + env in setup.py)
    fast_interval = float(scheduler.get("fast_interval", 10.0))
    fast_num = int(scheduler.get("fast_num_expirations", 5))

    rest_interval = float(scheduler.get("rest_interval", fast_interval))
    rest_num = int(scheduler.get("rest_num_expirations", fast_num))

    max_inflight = int(scheduler.get("max_inflight", 6))

    log(
        "main",
        "🧮",
        f"Scheduler: 0DTE={fast_num} exp(s) every {fast_interval}s, "
        f"rest={rest_num} exp(s) every {rest_interval}s, "
        f"max_inflight={max_inflight}",
    )

    last_fast = 0.0
    last_rest = 0.0
    workers: list[threading.Thread] = []

    while not stop_flag():
        now = time.time()

        # Prune finished workers
        alive: list[threading.Thread] = []
        for t in workers:
            if t.is_alive():
                alive.append(t)
        workers = alive
        inflight = len(workers)

        # 1) Fast lane — 0DTE, fire every fast_interval even if others still running
        if now - last_fast >= fast_interval and not stop_flag():
            if inflight < max_inflight:
                t = threading.Thread(
                    target=run_cycle,
                    args=(cfg, log, stop_flag, fast_num, "0DTE"),
                    daemon=True,
                )
                t.start()
                workers.append(t)
                last_fast = now
            else:
                log(
                    "main",
                    "⚠️",
                    f"Max inflight cycles reached ({max_inflight}), "
                    "skipping new 0DTE launch this tick.",
                )

        # 2) Rest lane — optional, likely off for pure 0DTE instance
        if (
            rest_num > fast_num
            and (now - last_rest) >= rest_interval
            and not stop_flag()
        ):
            if inflight < max_inflight:
                t = threading.Thread(
                    target=run_cycle,
                    args=(cfg, log, stop_flag, rest_num, "1-4DTE"),
                    daemon=True,
                )
                t.start()
                workers.append(t)
                last_rest = now
            else:
                log(
                    "main",
                    "⚠️",
                    f"Max inflight cycles reached ({max_inflight}), "
                    "skipping new 1-4DTE launch this tick.",
                )

        time.sleep(0.05)

    # Final cleanup — wait for any remaining workers
    for t in workers:
        t.join(timeout=1.0)

    log("main", "✅", "Scheduler loop exiting; Massive orchestrator stopped")


# ------------------------------------------------------------
# Async entrypoint for main.py
# ------------------------------------------------------------

async def run(config: Dict[str, Any]) -> None:
    """
    Async entrypoint for Massive orchestrator used by main.py.

    - Runs run_orchestrator(...) in a background thread.
    - Uses logutil.log for consistent logging.
    - Cooperates with asyncio cancellation (Ctrl+C in service main).

    main.py calls:

        orch_task = asyncio.create_task(
            orchestrator.run(config),
            name="massive-orchestrator",
        )
    """
    import logutil  # services/massive/logutil.py

    service_name = config.get("service_name", "massive")

    stop_event = threading.Event()

    def stop_flag() -> bool:
        return stop_event.is_set()

    def _log(stage: str, emoji: str, msg: str) -> None:
        # Map old-style log(stage, emoji, msg) into unified logutil format:
        #   [timestamp][service][STATUS] emoji message
        # Use INFO as default status; emojis still carry semantic weight.
        logutil.log(service_name, "INFO", emoji, f"{stage}: {msg}")

    def runner():
        try:
            run_orchestrator(config, _log, stop_flag)
        except Exception as e:
            logutil.log(service_name, "ERROR", "💥", f"orchestrator crashed: {e}")

    t = threading.Thread(target=runner, daemon=True)
    t.start()

    try:
        while t.is_alive():
            await asyncio.sleep(0.2)
    except asyncio.CancelledError:
        # Signal the scheduler to stop, then wait briefly for exit
        stop_event.set()
        t.join(timeout=2.0)
        raise