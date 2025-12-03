#!/usr/bin/env python3
"""
orchestrator.py — Massive orchestrator

Responsibilities:
- For a given configuration and number of expirations, launch
  massive_chain_loader.py once per symbol.
- Optionally run loaders in parallel (threads) or sequentially,
  based on workflow.threading_enabled.
- Stream child process output back through the main logger.

This module does NOT handle timing / cadence. It runs one "cycle"
and returns. Scheduling (e.g., 0DTE every 1s, 1–4DTE every 10s)
is handled by main.py using the scheduler block from setup_environment().
"""

import threading
import subprocess
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
        Global Massive configuration from setup_environment().
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

    redis_prefix = wf.get("redis_prefix", "chain")

    # Number of expirations for this run
    expirations = num_expirations

    # Strict inequality mode (pre-parsed in workflow as use_strict)
    strict_mode = str(wf.get("use_strict", False)).lower()

    # Redis + API key
    api_key = cfg.get("api_key") or ""
    redis_url = cfg["redis_market_url"]

    # Debug flags
    debug_rest = cfg.get("debug_rest", False)
    debug_threads = cfg.get("debug_threads", False)

    # Build command
    cmd = [
        py,
        script_path,
        "--symbols", symbol,
        "--strike-range", str(strike_range),
        "--redis-prefix", redis_prefix,
        "--api-key", api_key,
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
# Main orchestrator entrypoint (called from main.py)
# ------------------------------------------------------------

def run_orchestrator(
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

    Parameters
    ----------
    cfg : dict
        Global Massive configuration from setup_environment().
    log : callable
        Logger function from main.py: log(stage, emoji, msg).
    stop_flag : callable
        Zero-arg callable returning True if shutdown has been requested.
    num_expirations : int, optional
        Number of expirations to request. If None, falls back to
        workflow.num_expirations.
    label : str, optional
        Human-friendly label for logging (e.g., "0DTE", "1-4DTE").
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

    threads = []

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