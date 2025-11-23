#!/usr/bin/env python3
"""
MASSIVE Orchestrator — Market Data Engine
Coordinates:
  • chainfeed_worker      (fast ~2s)
  • convexity_worker      (suppressed)
  • volume_profile_worker (session-based VP — live updates)

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
from .volume_profile_worker import run_once as volume_profile_once


# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
def log(stage: str, emoji: str, msg: str):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}][massive|{stage}]{emoji} {msg}", flush=True)


# ---------------------------------------------------------------------
# Orchestrator Entry
# ---------------------------------------------------------------------
def run_orchestrator(config: dict, stop_flag):
    schedules = config["schedules"]

    # Extract schedules
    sec_chainfeed      = schedules["chainfeed"]
    sec_convexity      = schedules["convexity"]
    sec_volume_profile = schedules["volume_profile"]

    # Feature toggles
    enable_chainfeed      = schedules["enable_chainfeed"]
    enable_convexity      = schedules["enable_convexity"]
    enable_volume_profile = schedules["enable_volume_profile"]

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
                chainfeed_once()
                last_chainfeed = now
            except Exception as e:
                log("chainfeed", "❌", f"Error: {e}")
                traceback.print_exc()

        # ------------------ CONVEXITY WORKER (SUPPRESSED) ------------
        if enable_convexity and (now - last_convexity >= sec_convexity):
            try:
                log("convexity", "🧠", "Running convexity_once() [SUPPRESSED OUTPUT]…")
                convexity_once()
                last_convexity = now
            except Exception as e:
                log("convexity", "❌", f"Error: {e}")
                traceback.print_exc()

        # ------------------ VOLUME PROFILE WORKER --------------------
        # New session-based VP worker — publishes to sse:volume-profile
        if enable_volume_profile and (now - last_volume >= sec_volume_profile):
            try:
                log("volume", "📊", "Running volume_profile_once()…")
                volume_profile_once()
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