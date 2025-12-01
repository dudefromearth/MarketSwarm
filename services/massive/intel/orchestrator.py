#!/usr/bin/env python3
"""
MASSIVE Orchestrator — Market Data Engine
Coordinates:
  • chainfeed_worker      (fast ~2s)
  • convexity_worker      (suppressed)
  • vp_live_worker        (optimized incremental VP updates)

NO LONGER controls:
  • SSE gateway
  • API server
"""

import time
import traceback
from datetime import datetime, timezone

# Worker imports
from .chainfeed_worker import run_once as chainfeed_once
from .convexity_worker import run_once as convexity_once

# UPDATED: use new optimized VP worker
from .vp_live_worker import run_once as vp_live_once


# ---------------------------------------------------------------------
# Orchestrator Entry
# ---------------------------------------------------------------------
def run_orchestrator(config: dict, log, stop_flag):
    schedules = config.get("schedules", {}) or {}

    # Extract schedules (with safe defaults)
    sec_chainfeed      = schedules.get("chainfeed", 10)
    sec_convexity      = schedules.get("convexity", 60)
    sec_volume_profile = schedules.get("volume_profile", 60)

    # Feature toggles
    enable_chainfeed      = schedules.get("enable_chainfeed", True)
    enable_convexity      = schedules.get("enable_convexity", False)
    enable_volume_profile = schedules.get("enable_volume_profile", False)

    # Timers
    last_chainfeed  = 0
    last_convexity  = 0
    last_volume     = 0

    log("orchestrator", "🔥", "Massive orchestrator loop starting…")

    # ==================================================================
    # MAIN LOOP
    # ==================================================================
    while not stop_flag():

        now = time.time()

        # ------------------ CHAINFEED WORKER --------------------------
        if enable_chainfeed and (now - last_chainfeed >= sec_chainfeed):
            try:
                log("chainfeed", "📈", "Running chainfeed_once()…")
                chainfeed_once(config, log)
                last_chainfeed = now
            except Exception as e:
                log("chainfeed", "❌", f"Error: {e}")
                traceback.print_exc()

        # ------------------ CONVEXITY WORKER (SUPPRESSED) ------------
        if enable_convexity and (now - last_convexity >= sec_convexity):
            try:
                log("convexity", "🧠", "Running convexity_once() [SUPPRESSED OUTPUT]…")
                convexity_once(config, log)
                last_convexity = now
            except Exception as e:
                log("convexity", "❌", f"Error: {e}")
                traceback.print_exc()

        # ------------------ VOLUME PROFILE WORKER --------------------
        # Updated: call new vp_live_worker
        if enable_volume_profile and (now - last_volume >= sec_volume_profile):
            try:
                log("volume", "📊", "Running vp_live_once()…")
                vp_live_once(config, log)
                last_volume = now
            except Exception as e:
                log("volume", "❌", f"Error: {e}")
                traceback.print_exc()

        # Gentle yield
        time.sleep(0.2)

    # ==================================================================
    # SHUTDOWN
    # ==================================================================
    log("orchestrator", "🛑", "Stopping MASSIVE orchestrator…")
    log("orchestrator", "🙏", "MASSIVE orchestrator exited cleanly.")