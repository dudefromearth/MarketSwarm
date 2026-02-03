#!/usr/bin/env python3
# services/massive/intel/model_builders/trade_selector.py
"""
Trade Selector Model Builder

Evaluates heatmap tiles to find optimal butterfly entries based on:
1. R:R Score (25%) - Risk/Reward ratio with realistic constraints
2. Convexity Score (25%) - Gamma exposure relative to premium paid
3. Width Fit Score (25%) - VIX playbook regime alignment
4. Gamma Alignment Score (25%) - Proximity to GEX levels

Hard Rules (from Big Ass Fly Playbook):
- Debit must be ≤ 5% of width (extreme asymmetry requirement)
- Width ranges defined by VIX regime
- DTE constraints by regime

Publishes to: massive:selector:model:{symbol}:latest
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from redis.asyncio import Redis


class TradeSelectorModelBuilder:
    """
    Calculates composite scores for heatmap tiles and publishes top recommendations.
    """

    ANALYTICS_KEY = "massive:model:analytics"
    BUILDER_NAME = "trade_selector"

    # Score weights
    WEIGHT_R2R = 0.25
    WEIGHT_CONVEXITY = 0.25
    WEIGHT_WIDTH_FIT = 0.25
    WEIGHT_GAMMA_ALIGNMENT = 0.25

    # ==========================================================================
    # Big Ass Fly Playbook Constants
    # ==========================================================================

    # Hard filter: debit must be ≤ this percentage of width
    # 5% = extreme asymmetry (e.g., 30-wide max debit $1.50)
    MAX_DEBIT_PCT = 0.05

    # VIX regime thresholds
    VIX_CHAOS_CUT = 32      # Chaos: VIX ≥ 32
    VIX_GOLD2_CUT = 23      # Goldilocks 2: VIX 23-32
    VIX_GOLD1_CUT = 17      # Goldilocks 1: VIX 17-23
    # Below 17 = Zombieland

    # Width ranges by regime: (min_width, max_width)
    # From playbook chart - Classic OTM Fly Width Guide
    WIDTH_CHAOS = (50, 100)       # Chaos: 50+ wide
    WIDTH_GOLDILOCKS_2 = (40, 50) # Goldilocks 2: 40-50 wide
    WIDTH_GOLDILOCKS_1 = (30, 40) # Goldilocks 1: 30-40 wide
    WIDTH_ZOMBIELAND = (20, 30)   # Zombieland: 20-30 wide

    # DTE constraints by regime: (min_dte, max_dte)
    DTE_CHAOS = (1, 3)            # Chaos: 1-3 DTE (need time for vol to settle)
    DTE_GOLDILOCKS_2 = (0, 2)     # Goldilocks 2: 0-2 DTE
    DTE_GOLDILOCKS_1 = (0, 1)     # Goldilocks 1: 0-1 DTE
    DTE_ZOMBIELAND = (0, 1)       # Zombieland: 0-1 DTE

    # ==========================================================================
    # Edge Case Strategies (not regimes)
    # ==========================================================================
    # TimeWarp: Low VIX strategy with accelerated decay, use 1-2 DTE to capture
    # premium before too much decays. Narrower flies work here.
    TIMEWARP_WIDTH = (10, 20)     # Narrower flies for TimeWarp strategy
    TIMEWARP_DTE = (1, 2)         # 1-2 DTE to capture premium before rapid decay

    # ==========================================================================
    # Gamma Scalp Mode
    # ==========================================================================
    # Late-day, high-gamma, structural squeeze play
    # Works best in low VIX, but can work in high VIX (smaller window)
    # Higher VIX = closer to expiration the opportunity becomes

    GAMMA_SCALP_WIDTH = (15, 25)  # Narrow flies for high gamma
    GAMMA_SCALP_DTE = 0           # 0DTE only
    GAMMA_SCALP_MAX_DISTANCE_PCT = 0.5  # Max 0.5% from ATM (near ATM, not OTM)

    # Gamma scalp timing windows by regime (hour ranges in ET, fractional)
    # Lower VIX = earlier window, Higher VIX = later (closer to expiration)
    GAMMA_SCALP_WINDOWS = {
        "zombieland": (13.5, 15.5),   # 1:30 PM - 3:30 PM (wide window in low vol)
        "goldilocks_1": (14.5, 15.5), # 2:30 PM - 3:30 PM
        "goldilocks_2": (15.0, 15.75), # 3:00 PM - 3:45 PM (tighter)
        "chaos": (15.25, 15.75),      # 3:15 PM - 3:45 PM (very tight window)
    }

    # Gamma scalp profit style by regime
    # Low VIX = sniper (quick Zone 1-2), High VIX = net caster (Zone 2-3, pins)
    GAMMA_SCALP_STYLE = {
        "zombieland": {"style": "sniper", "target_zones": [1, 2], "hold_tolerance": "low"},
        "goldilocks_1": {"style": "balanced", "target_zones": [1, 2], "hold_tolerance": "medium"},
        "goldilocks_2": {"style": "net_caster", "target_zones": [2, 3], "hold_tolerance": "high"},
        "chaos": {"style": "net_caster", "target_zones": [2, 3], "hold_tolerance": "high"},
    }

    # ==========================================================================
    # Expected Move (EM) Tracking
    # ==========================================================================
    # EM gets exceeded ~19-20% of the time - this is where convexity pays off
    # Most traders abandon positions, but these breaches are the profit engine

    EM_BASE_BREACH_RATE = 0.195  # 19.5% base rate of EM breach

    # Breach probability adjustments by regime
    # Higher VIX = more likely to see outsized moves
    EM_BREACH_REGIME_MULT = {
        "chaos": 1.4,        # 27% breach rate in chaos
        "goldilocks_2": 1.2, # 23% breach rate
        "goldilocks_1": 1.0, # 19.5% baseline
        "zombieland": 0.85,  # 16.5% in low vol
    }

    # Session adjustments - morning has more vol, more breaches
    EM_BREACH_SESSION_MULT = {
        "premarket": 0.8,
        "morning": 1.15,     # Morning session more likely to breach
        "afternoon": 0.95,
        "closing": 1.1,      # Closing can see squeezes
    }

    # Payoff zone distribution (from real data)
    PAYOFF_ZONES = {
        "zone_0": {"probability": 0.50, "return_range": (0, 0), "label": "Loss"},
        "zone_1": {"probability": 0.375, "return_range": (0.5, 2.5), "label": "Standard Win"},
        "zone_2": {"probability": 0.10, "return_range": (2.5, 4.5), "label": "Strong Win"},
        "zone_3": {"probability": 0.025, "return_range": (8.0, 19.0), "label": "Pin Trade"},
    }

    # R:R expectations by DTE
    R2R_EXPECTATIONS = {
        0: {"typical": (10, 12), "max": (15, 18)},     # 0DTE: 10-12 typical, up to 15-18
        1: {"typical": (12, 15), "max": (18, 22)},     # 1DTE
        2: {"typical": (15, 20), "max": (22, 28)},     # 2DTE
        3: {"typical": (18, 25), "max": (28, 35)},     # 3-5DTE range
        5: {"typical": (25, 35), "max": (35, 50)},     # 5-10DTE range
    }

    # ==========================================================================
    # Trading Sessions (Eastern Time)
    # ==========================================================================
    # Sessions help compartmentalize volatility behaviors
    SESSION_PREMARKET = ("premarket", 7, 9.5)      # 7:00 AM - 9:30 AM ET
    SESSION_MORNING = ("morning", 9.5, 12.5)       # 9:30 AM - 12:30 PM ET
    SESSION_AFTERNOON = ("afternoon", 12.5, 14.5)  # 12:30 PM - 2:30 PM ET
    SESSION_CLOSING = ("closing", 14.5, 16)        # 2:30 PM - 4:00 PM ET

    # Session characteristics:
    # - Morning: Highest avg volatility, best for 0DTE entries, get ahead of moves
    # - Afternoon: Most trades exercised (late morning to early afternoon)
    # - Closing: Outlier territory - trades here tend to pay off big if they work

    # Legacy thresholds (kept for compatibility)
    VIX_LOWER_CUT = 17
    VIX_UPPER_CUT = 32
    AFTERNOON_HOUR = 12  # Noon ET - for legacy regime detection

    def __init__(self, config: Dict[str, Any], logger) -> None:
        self.config = config
        self.logger = logger

        self.symbols = [
            s.strip()
            for s in config.get("MASSIVE_CHAIN_SYMBOLS", "I:SPX,I:NDX").split(",")
            if s.strip()
        ]

        self.interval_sec = int(config.get("MASSIVE_SELECTOR_INTERVAL_SEC", "1"))
        self.model_ttl_sec = int(config.get("MASSIVE_SELECTOR_TTL_SEC", "3600"))
        self.top_n = int(config.get("MASSIVE_SELECTOR_TOP_N", "10"))

        self.market_redis_url = config["buses"]["market-redis"]["url"]
        self._redis: Redis | None = None

        self.logger.info(
            f"[TRADE_SELECTOR INIT] symbols={self.symbols} interval={self.interval_sec}s top_n={self.top_n}",
            emoji="🎯",
        )

    async def _redis_conn(self) -> Redis:
        if not self._redis:
            self._redis = Redis.from_url(self.market_redis_url, decode_responses=True)
        return self._redis

    # ------------------------------------------------------------------
    # Data Loading
    # ------------------------------------------------------------------

    async def _load_spot(self, symbol: str) -> Optional[float]:
        """Load current spot price."""
        r = await self._redis_conn()
        raw = await r.get(f"massive:model:spot:{symbol}")
        if not raw:
            return None
        try:
            return float(json.loads(raw).get("value"))
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    async def _load_vix(self) -> Optional[float]:
        """Load current VIX value from vexy_ai signals."""
        r = await self._redis_conn()
        raw = await r.get("vexy_ai:signals:latest")
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return float(data.get("vix") or data.get("VIX", 15))
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    async def _load_heatmap(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Load unified heatmap model for symbol."""
        r = await self._redis_conn()
        key = f"massive:heatmap:model:{symbol}:latest"
        raw = await r.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def _load_gex_by_strike(self, symbol: str) -> Dict[float, Dict[str, float]]:
        """
        Load and aggregate GEX by strike.
        Returns {strike: {"calls": gex, "puts": gex, "net": net_gex}}.
        """
        r = await self._redis_conn()
        calls_raw = await r.get(f"massive:gex:model:{symbol}:calls")
        puts_raw = await r.get(f"massive:gex:model:{symbol}:puts")

        by_strike: Dict[float, Dict[str, float]] = {}

        if calls_raw:
            try:
                calls = json.loads(calls_raw)
                for exp, strikes in calls.get("expirations", {}).items():
                    for strike_str, gex in strikes.items():
                        strike = float(strike_str)
                        if strike not in by_strike:
                            by_strike[strike] = {"calls": 0.0, "puts": 0.0, "net": 0.0}
                        by_strike[strike]["calls"] += gex
            except json.JSONDecodeError:
                pass

        if puts_raw:
            try:
                puts = json.loads(puts_raw)
                for exp, strikes in puts.get("expirations", {}).items():
                    for strike_str, gex in strikes.items():
                        strike = float(strike_str)
                        if strike not in by_strike:
                            by_strike[strike] = {"calls": 0.0, "puts": 0.0, "net": 0.0}
                        # Puts stored positive, but represent negative gamma
                        by_strike[strike]["puts"] -= gex
            except json.JSONDecodeError:
                pass

        # Calculate net
        for strike in by_strike:
            by_strike[strike]["net"] = by_strike[strike]["calls"] + by_strike[strike]["puts"]

        return by_strike

    async def _load_bias_lfi(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Load bias/LFI model with GEX flip level."""
        r = await self._redis_conn()
        raw = await r.get(f"massive:bias_lfi:model:{symbol}:latest")
        if not raw:
            raw = await r.get("massive:bias_lfi:model:latest")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    # ------------------------------------------------------------------
    # VIX Regime Logic (Big Ass Fly Playbook)
    # ------------------------------------------------------------------

    def _get_vix_regime(self, vix: float, current_hour: int) -> Tuple[str, Optional[str]]:
        """
        Get VIX regime and special condition/strategy based on playbook.
        Returns (regime, special_condition).

        Regimes (based on VIX level):
        - chaos: VIX ≥ 32 (high volatility, slow decay, wide flies)
        - goldilocks_2: VIX 23-32 (elevated vol)
        - goldilocks_1: VIX 17-23 (normal vol)
        - zombieland: VIX < 17 (low vol, fast decay)

        Special conditions/strategies (edge cases, not regimes):
        - batman: VIX ≥ 40 (extreme chaos)
        - timewarp: Low VIX with accelerated decay opportunity
        - gamma_scalp: Late session low-vol scalping opportunity
        """
        is_afternoon = current_hour >= self.AFTERNOON_HOUR

        if vix >= self.VIX_CHAOS_CUT:
            regime = "chaos"
            special = "batman" if vix >= 40 else None
        elif vix >= self.VIX_GOLD2_CUT:
            regime = "goldilocks_2"
            special = None
        elif vix >= self.VIX_GOLD1_CUT:
            regime = "goldilocks_1"
            special = None
        else:
            # Zombieland regime
            regime = "zombieland"
            # TimeWarp is a strategy opportunity in low VIX
            if vix <= 15:
                special = "timewarp"
            elif is_afternoon:
                special = "gamma_scalp"
            else:
                special = None

        return regime, special

    def _get_ideal_width_range(self, regime: str, special: Optional[str] = None) -> Tuple[int, int]:
        """
        Get ideal width range based on VIX regime from playbook.
        Returns (min_width, max_width).

        Note: TimeWarp is a strategy, not a regime. When timewarp strategy
        is active in zombieland, narrower widths are preferred.
        """
        if regime == "chaos":
            return self.WIDTH_CHAOS
        elif regime == "goldilocks_2":
            return self.WIDTH_GOLDILOCKS_2
        elif regime == "goldilocks_1":
            return self.WIDTH_GOLDILOCKS_1
        else:  # zombieland
            # If timewarp strategy is active, use narrower widths
            if special == "timewarp":
                return self.TIMEWARP_WIDTH
            return self.WIDTH_ZOMBIELAND

    def _get_ideal_dte_range(self, regime: str, special: Optional[str] = None) -> Tuple[int, int]:
        """
        Get ideal DTE range based on VIX regime from playbook.
        Returns (min_dte, max_dte).

        Note: TimeWarp strategy uses 1-2 DTE to capture premium before rapid decay.
        """
        if regime == "chaos":
            return self.DTE_CHAOS
        elif regime == "goldilocks_2":
            return self.DTE_GOLDILOCKS_2
        elif regime == "goldilocks_1":
            return self.DTE_GOLDILOCKS_1
        else:  # zombieland
            # If timewarp strategy is active, use 1-2 DTE
            if special == "timewarp":
                return self.TIMEWARP_DTE
            return self.DTE_ZOMBIELAND

    def _passes_debit_filter(self, width: int, debit: float) -> bool:
        """
        Hard filter: debit must be ≤ 5% of width for extreme asymmetry.
        E.g., 30-wide fly max debit = $1.50
        """
        max_debit = width * self.MAX_DEBIT_PCT
        return debit <= max_debit

    def _get_session(self, current_hour: float) -> Tuple[str, dict]:
        """
        Get current trading session based on hour (ET).

        Sessions:
        - premarket: 7:00 AM - 9:30 AM (preparation, limited liquidity)
        - morning: 9:30 AM - 12:30 PM (highest vol, best 0DTE entries)
        - afternoon: 12:30 PM - 2:30 PM (exercise window, vol dropping)
        - closing: 2:30 PM - 4:00 PM (outlier territory, big payoffs possible)

        Returns (session_name, session_info).
        """
        sessions = [
            self.SESSION_PREMARKET,
            self.SESSION_MORNING,
            self.SESSION_AFTERNOON,
            self.SESSION_CLOSING,
        ]

        for name, start, end in sessions:
            if start <= current_hour < end:
                return name, {
                    "name": name,
                    "start": start,
                    "end": end,
                    "is_entry_optimal": name == "morning",
                    "is_exercise_window": name in ("morning", "afternoon") and current_hour >= 11,
                    "is_outlier_zone": name == "closing",
                }

        # Outside market hours
        if current_hour < 7:
            return "overnight", {"name": "overnight", "is_entry_optimal": False}
        else:
            return "after_hours", {"name": "after_hours", "is_entry_optimal": False}

    def _get_time_decay_factor(self, session: str, regime: str) -> float:
        """
        Get time-of-day decay acceleration factor based on session and regime.

        Decay behavior by session:
        - Morning: Normal decay, highest volatility
        - Afternoon: Accelerating decay, vol dropping
        - Closing: Rapid decay, gamma intensifies

        In low VIX regimes, decay accelerates more aggressively.
        In high VIX regimes, decay is more consistent throughout day.

        Returns multiplier for scoring adjustments (1.0 = normal, >1.0 = faster decay).
        """
        # Base decay by session
        session_decay = {
            "premarket": 0.8,   # Slower before open
            "morning": 1.0,    # Normal - baseline
            "afternoon": 1.3,  # Accelerating
            "closing": 1.6,    # Rapid decay
            "overnight": 0.5,
            "after_hours": 0.5,
        }

        base = session_decay.get(session, 1.0)

        # Regime modifier - low vol = faster decay
        regime_modifier = {
            "zombieland": 1.2,    # Fast decay in low vol
            "goldilocks_1": 1.1,  # Moderate
            "goldilocks_2": 1.0,  # Normal
            "chaos": 0.9,         # Slow decay (vol stays elevated)
        }

        modifier = regime_modifier.get(regime, 1.0)

        return round(base * modifier, 2)

    def _score_session_timing(self, dte: int, session: str, session_info: dict) -> float:
        """
        Score based on session timing for trade entry.

        Key principles:
        - 0DTE trades best taken in morning session (higher vol, ahead of moves)
        - Most trades exercised late morning to early afternoon
        - Closing session trades are outliers but can pay big

        Returns score 0-100.
        """
        if dte == 0:
            # 0DTE scoring - timing is critical
            if session == "morning":
                # Optimal: morning session for 0DTE
                return 95.0
            elif session == "premarket":
                # Good: getting positioned early
                return 80.0
            elif session == "afternoon":
                # Risky: past prime entry window
                return 50.0
            elif session == "closing":
                # Outlier zone: high risk but can pay big
                # Score lower but not disqualifying
                return 40.0
            else:
                return 30.0
        elif dte == 1:
            # 1DTE - more flexible timing
            if session in ("morning", "afternoon"):
                return 85.0
            elif session == "closing":
                # Late entry for 1DTE is fine - have time
                return 75.0
            else:
                return 60.0
        else:
            # Multi-day - timing less critical
            return 70.0

    # ------------------------------------------------------------------
    # Gamma Scalp Mode
    # ------------------------------------------------------------------

    def _is_gamma_scalp_window(self, current_hour: float, regime: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if current time is within the gamma scalp window for this regime.

        Returns (is_active, window_info).
        """
        window = self.GAMMA_SCALP_WINDOWS.get(regime)
        if not window:
            return False, {"active": False, "reason": "no_window_for_regime"}

        start_hour, end_hour = window
        is_active = start_hour <= current_hour <= end_hour

        if is_active:
            # Calculate how far into the window we are (0-1)
            window_progress = (current_hour - start_hour) / (end_hour - start_hour)
            time_remaining = end_hour - current_hour

            return True, {
                "active": True,
                "window_start": start_hour,
                "window_end": end_hour,
                "progress": round(window_progress, 2),
                "time_remaining_hrs": round(time_remaining, 2),
                "urgency": "high" if window_progress > 0.7 else "medium" if window_progress > 0.4 else "low",
            }
        else:
            if current_hour < start_hour:
                return False, {
                    "active": False,
                    "reason": "before_window",
                    "starts_in_hrs": round(start_hour - current_hour, 2),
                }
            else:
                return False, {
                    "active": False,
                    "reason": "after_window",
                }

    def _score_gamma_scalp(
        self,
        strike: float,
        width: int,
        debit: float,
        spot: float,
        regime: str,
        window_info: Dict[str, Any],
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Score a tile for gamma scalp suitability.

        Gamma scalp criteria:
        - Near ATM (within 0.5% of spot)
        - Narrow width (15-25)
        - 0DTE only
        - Cheap debit (high gamma)
        - Within timing window

        Returns (score, details).
        """
        details = {
            "is_candidate": False,
            "disqualify_reasons": [],
        }

        # Check width
        min_w, max_w = self.GAMMA_SCALP_WIDTH
        if not (min_w <= width <= max_w):
            details["disqualify_reasons"].append(f"width_{width}_not_in_{min_w}-{max_w}")

        # Check distance from ATM
        distance_from_spot = abs(strike - spot)
        distance_pct = (distance_from_spot / spot) * 100
        max_distance_pct = self.GAMMA_SCALP_MAX_DISTANCE_PCT

        if distance_pct > max_distance_pct:
            details["disqualify_reasons"].append(f"too_far_from_atm_{distance_pct:.2f}%")

        # If disqualified, return 0
        if details["disqualify_reasons"]:
            return 0.0, details

        # It's a candidate - calculate score
        details["is_candidate"] = True
        details["distance_from_spot"] = round(distance_from_spot, 2)
        details["distance_pct"] = round(distance_pct, 3)

        # Scoring components for gamma scalp

        # 1. ATM proximity (40%) - closer to ATM = better gamma
        if distance_pct <= 0.1:
            atm_score = 100.0
        elif distance_pct <= 0.2:
            atm_score = 90.0
        elif distance_pct <= 0.3:
            atm_score = 75.0
        else:
            atm_score = 60.0

        # 2. Width efficiency (30%) - narrower = more gamma per dollar
        width_score = 100.0 - ((width - min_w) / (max_w - min_w)) * 40  # 100 at 15, 60 at 25

        # 3. Debit cheapness (30%) - cheaper = better risk profile
        # For gamma scalp, we want very cheap flies
        debit_pct = (debit / width) * 100
        if debit_pct <= 3:
            debit_score = 100.0
        elif debit_pct <= 4:
            debit_score = 85.0
        elif debit_pct <= 5:
            debit_score = 70.0
        else:
            debit_score = 50.0

        # Combine scores
        gamma_scalp_score = (
            atm_score * 0.40 +
            width_score * 0.30 +
            debit_score * 0.30
        )

        # Apply urgency boost if late in window
        if window_info.get("urgency") == "high":
            gamma_scalp_score *= 1.1  # 10% boost for urgency

        # Get profit style for this regime
        style_info = self.GAMMA_SCALP_STYLE.get(regime, {})

        details["scores"] = {
            "atm_proximity": round(atm_score, 1),
            "width_efficiency": round(width_score, 1),
            "debit_cheapness": round(debit_score, 1),
        }
        details["style"] = style_info.get("style", "balanced")
        details["target_zones"] = style_info.get("target_zones", [1, 2])
        details["hold_tolerance"] = style_info.get("hold_tolerance", "medium")

        return min(100.0, round(gamma_scalp_score, 1)), details

    # ------------------------------------------------------------------
    # Expected Move (EM) Calculations
    # ------------------------------------------------------------------

    def _calculate_expected_move(self, spot: float, vix: float, dte: int = 0) -> float:
        """
        Calculate Expected Move based on VIX.

        Formula: EM = Spot × (VIX / 100) × √(DTE / 252)
        For 0DTE, use 1 day.

        Returns expected move in points.
        """
        days = max(1, dte) if dte == 0 else dte
        em = spot * (vix / 100) * math.sqrt(days / 252)
        return round(em, 2)

    def _estimate_em_breach_probability(
        self,
        regime: str,
        session: str,
        vix: float,
    ) -> Dict[str, Any]:
        """
        Estimate probability of Expected Move breach for current conditions.

        Base rate: 19.5% (EM exceeded ~1 in 5 days)
        Adjusted for regime, session, and VIX level.

        Returns dict with breach probability and context.
        """
        base_rate = self.EM_BASE_BREACH_RATE

        # Regime adjustment
        regime_mult = self.EM_BREACH_REGIME_MULT.get(regime, 1.0)

        # Session adjustment
        session_mult = self.EM_BREACH_SESSION_MULT.get(session, 1.0)

        # VIX level adjustment - extreme VIX increases breach likelihood
        vix_mult = 1.0
        if vix >= 40:
            vix_mult = 1.5  # Batman territory - expect breaches
        elif vix >= 30:
            vix_mult = 1.25
        elif vix <= 12:
            vix_mult = 0.8  # Ultra-low vol, moves compressed

        # Calculate adjusted breach probability
        breach_prob = base_rate * regime_mult * session_mult * vix_mult
        breach_prob = min(0.45, breach_prob)  # Cap at 45%

        # Categorize breach likelihood
        if breach_prob >= 0.30:
            likelihood = "high"
            color = "green"
        elif breach_prob >= 0.22:
            likelihood = "elevated"
            color = "yellow"
        elif breach_prob >= 0.15:
            likelihood = "normal"
            color = "neutral"
        else:
            likelihood = "low"
            color = "red"

        return {
            "breach_probability": round(breach_prob, 3),
            "breach_pct": round(breach_prob * 100, 1),
            "likelihood": likelihood,
            "color": color,
            "factors": {
                "base_rate": base_rate,
                "regime_mult": regime_mult,
                "session_mult": session_mult,
                "vix_mult": vix_mult,
            },
        }

    def _get_r2r_expectations(self, dte: int) -> Dict[str, Tuple[int, int]]:
        """
        Get expected R:R ranges for given DTE.

        Returns dict with typical and max R:R ranges.
        """
        # Find closest DTE key
        dte_keys = sorted(self.R2R_EXPECTATIONS.keys())
        closest_dte = min(dte_keys, key=lambda x: abs(x - dte))

        return self.R2R_EXPECTATIONS[closest_dte]

    def _calculate_convexity_opportunity(
        self,
        breach_prob: float,
        r2r_ratio: float,
        dte: int,
    ) -> Dict[str, Any]:
        """
        Calculate convexity opportunity score.

        Combines EM breach probability with R:R to estimate
        the expected value of the convexity play.

        Key insight: 50% of trades lose, but Zone 1 (37.5%) offsets losses.
        The 12.5% Zone 2+3 trades are pure profit, aligned with EM breaches.
        """
        # Get R:R expectations for this DTE
        r2r_exp = self._get_r2r_expectations(dte)
        typical_low, typical_high = r2r_exp["typical"]
        max_low, max_high = r2r_exp["max"]

        # Score the R:R relative to expectations
        if r2r_ratio >= max_high:
            r2r_quality = "exceptional"
            r2r_score = 100
        elif r2r_ratio >= max_low:
            r2r_quality = "excellent"
            r2r_score = 90
        elif r2r_ratio >= typical_high:
            r2r_quality = "good"
            r2r_score = 75
        elif r2r_ratio >= typical_low:
            r2r_quality = "acceptable"
            r2r_score = 60
        else:
            r2r_quality = "below_target"
            r2r_score = 40

        # Convexity opportunity combines breach probability with R:R quality
        # Higher breach prob + better R:R = better opportunity
        convexity_score = (breach_prob * 100) * (r2r_score / 100)

        # Expected value estimation
        # Zone distribution: 50% lose, 37.5% small win, 10% medium, 2.5% big
        # Simplified EV: (win_rate * avg_win_multiple) - (loss_rate * 1)
        win_rate = 0.50
        avg_win_mult = 1.5 + (breach_prob * 3)  # Higher breach = higher avg win
        ev_per_risk = (win_rate * avg_win_mult) - (0.50 * 1.0)

        return {
            "convexity_score": round(convexity_score, 1),
            "r2r_quality": r2r_quality,
            "r2r_vs_typical": f"{r2r_ratio:.1f} vs {typical_low}-{typical_high}",
            "r2r_vs_max": f"{r2r_ratio:.1f} vs {max_low}-{max_high}",
            "ev_per_risk": round(ev_per_risk, 2),
            "ev_positive": ev_per_risk > 0,
        }

    # ------------------------------------------------------------------
    # Scoring Functions
    # ------------------------------------------------------------------

    def _score_r2r(self, width: int, debit: float) -> float:
        """
        Calculate R:R score (0-100).
        R:R = (width - debit) / debit
        Score = min(95, 30 * log2(r2r + 1))
        """
        if debit <= 0.10:
            return 0.0  # Won't fill

        r2r = (width - debit) / debit
        if r2r <= 0:
            return 0.0

        score = min(95, 30 * math.log2(r2r + 1))

        # Penalty for likely illiquid
        if debit < 0.50:
            score *= (debit / 0.50)

        return max(0, score)

    def _score_convexity(
        self,
        strike: float,
        width: int,
        debit: float,
        all_debits: Dict[str, float],
        gex_by_strike: Dict[float, Dict[str, float]],
    ) -> float:
        """
        Calculate convexity score (0-100).
        Three sub-components:
        - Debit Gradient (40%): % price change vs adjacent strikes
        - Gamma Alignment (35%): Wings near positive GEX = support
        - Debit Efficiency (25%): Value per dollar paid
        """
        # Debit gradient - compare to adjacent strikes
        gradient_score = 50.0  # Default
        adjacent_debits = []

        for adj in [-5, 5, -10, 10]:  # Check nearby strikes
            adj_strike = strike + adj
            adj_key = str(int(adj_strike))
            if adj_key in all_debits:
                adjacent_debits.append(all_debits[adj_key])

        if adjacent_debits and debit > 0:
            avg_adjacent = sum(adjacent_debits) / len(adjacent_debits)
            if avg_adjacent > 0:
                # How much cheaper are we than neighbors?
                gradient = (avg_adjacent - debit) / avg_adjacent * 100
                gradient_score = min(95, max(0, 50 + gradient * 2))

        # Gamma support - are wings near positive GEX?
        gamma_support_score = 50.0
        low_wing = strike - width
        high_wing = strike + width

        wing_gex_support = 0
        for wing in [low_wing, high_wing]:
            for offset in range(-5, 6, 5):  # Check 5 pts around wing
                check_strike = wing + offset
                if check_strike in gex_by_strike:
                    net_gex = gex_by_strike[check_strike]["net"]
                    if net_gex > 0:
                        wing_gex_support += 15  # Positive GEX = support

        gamma_support_score = min(95, 50 + wing_gex_support)

        # Debit efficiency - max profit per dollar at risk
        efficiency_score = 50.0
        if debit > 0:
            max_profit = width - debit
            efficiency = max_profit / debit
            efficiency_score = min(95, 30 * math.log2(efficiency + 1))

        # Combine sub-components
        convexity = (
            gradient_score * 0.40 +
            gamma_support_score * 0.35 +
            efficiency_score * 0.25
        )

        return convexity

    def _score_width_fit(
        self,
        width: int,
        dte: int,
        regime: str,
        special: Optional[str],
        decay_factor: float,
        session: str,
        session_info: dict,
    ) -> float:
        """
        Calculate width fit score (0-100).
        Based on Big Ass Fly Playbook width, DTE, and session guidelines.

        Scoring components:
        - Width match to regime (40%)
        - DTE match to regime (25%)
        - Session timing (20%) - 0DTE best in morning, etc.
        - Wider bonus (15%) - wider trades have better payoff curves
        """
        # --- Width scoring (40%) ---
        min_w, max_w = self._get_ideal_width_range(regime, special)

        if min_w <= width <= max_w:
            # Perfect fit
            width_score = 95.0
        elif width > max_w:
            # Wider than ideal - still good, slight penalty
            overage = width - max_w
            width_score = max(70.0, 95.0 - overage * 0.5)
        elif width >= min_w - 5:
            # Within 5 pts below minimum
            width_score = 75.0
        elif width >= min_w - 10:
            # Within 10 pts below minimum
            width_score = 55.0
        else:
            # Way too narrow for regime
            width_score = 30.0

        # --- DTE scoring (25%) ---
        min_dte, max_dte = self._get_ideal_dte_range(regime, special)

        if min_dte <= dte <= max_dte:
            # Perfect DTE for regime
            dte_score = 95.0
        elif dte == max_dte + 1:
            # One day over - acceptable
            dte_score = 70.0
        elif regime == "chaos" and dte == 0:
            # 0 DTE in chaos is risky (need time for vol)
            dte_score = 40.0
        elif regime == "zombieland" and dte > 1:
            # Multi-day in low vol wastes decay opportunity
            dte_score = 50.0
        else:
            dte_score = 60.0

        # --- Session timing (20%) ---
        session_score = self._score_session_timing(dte, session, session_info)

        # --- Wider bonus (15%) ---
        # From study: ROI scales non-linearly with width
        # 10-wide = 70% ROI, 35-wide = 356% ROI
        # Bonus rewards wider trades that maintain R:R
        if width >= 50:
            wider_bonus = 95.0
        elif width >= 40:
            wider_bonus = 85.0
        elif width >= 30:
            wider_bonus = 70.0
        elif width >= 20:
            wider_bonus = 55.0
        else:
            wider_bonus = 40.0

        # Apply decay factor - in fast decay conditions, narrower trades
        # can work if quick in/out, so reduce width penalty slightly
        if decay_factor > 1.0 and width < min_w:
            width_score = min(width_score * 1.1, 70.0)

        # Combine components
        score = (
            width_score * 0.40 +
            dte_score * 0.25 +
            session_score * 0.20 +
            wider_bonus * 0.15
        )

        return score

    def _score_gamma_alignment(
        self,
        strike: float,
        width: int,
        side: str,
        spot: float,
        gex_by_strike: Dict[float, Dict[str, float]],
        bias_lfi: Optional[Dict[str, Any]],
    ) -> float:
        """
        Calculate gamma alignment score (0-100).
        - Gamma Magnet proximity (40%): center near max net GEX
        - Zero Gamma position (30%): calls above ZG, puts below ZG
        - Wing GEX support (30%): wings near positive GEX strikes
        """
        # Find key GEX levels
        gamma_magnet = None
        zero_gamma = None

        if bias_lfi:
            gamma_magnet = bias_lfi.get("max_net_gex_strike")
            zero_gamma = bias_lfi.get("gex_flip_level")

        # 1. Gamma Magnet proximity (40%)
        magnet_score = 60.0  # Default
        if gamma_magnet is not None:
            distance = abs(strike - gamma_magnet)
            if distance <= 10:
                magnet_score = 95.0
            elif distance <= 25:
                magnet_score = 80.0
            elif distance <= 50:
                magnet_score = 60.0
            else:
                magnet_score = 40.0

        # 2. Zero Gamma position (30%)
        zg_score = 50.0  # Neutral
        if zero_gamma is not None:
            if side == "call" and strike > zero_gamma:
                # Calls above ZG = good
                zg_score = 80.0
            elif side == "put" and strike < zero_gamma:
                # Puts below ZG = good
                zg_score = 80.0
            else:
                # Wrong side of ZG
                zg_score = 30.0

        # 3. Wing GEX support (30%)
        wing_score = 50.0
        low_wing = strike - width
        high_wing = strike + width

        for wing in [low_wing, high_wing]:
            if wing in gex_by_strike:
                net_gex = gex_by_strike[wing]["net"]
                if net_gex > 0:
                    wing_score += 15  # Wings at positive GEX = support

        wing_score = min(95, wing_score)

        # Combine
        gamma_alignment = (
            magnet_score * 0.40 +
            zg_score * 0.30 +
            wing_score * 0.30
        )

        return gamma_alignment

    def _calculate_composite_score(
        self,
        r2r_score: float,
        convexity_score: float,
        width_fit_score: float,
        gamma_alignment_score: float,
    ) -> float:
        """Calculate weighted composite score."""
        return (
            self.WEIGHT_R2R * r2r_score +
            self.WEIGHT_CONVEXITY * convexity_score +
            self.WEIGHT_WIDTH_FIT * width_fit_score +
            self.WEIGHT_GAMMA_ALIGNMENT * gamma_alignment_score
        )

    def _calculate_confidence(
        self,
        has_gex: bool,
        has_bias_lfi: bool,
        debit: float,
    ) -> float:
        """Calculate data quality confidence (0-1)."""
        confidence = 0.5  # Base confidence

        if has_gex:
            confidence += 0.25
        if has_bias_lfi:
            confidence += 0.15

        # Higher debit = more liquid = more confident
        if debit >= 1.0:
            confidence += 0.10

        return min(1.0, confidence)

    # ------------------------------------------------------------------
    # Main Build Logic
    # ------------------------------------------------------------------

    async def _build_once(self) -> None:
        """Main build cycle."""
        r = await self._redis_conn()
        t_start = time.monotonic()

        try:
            for symbol in self.symbols:
                # Load common data
                spot = await self._load_spot(symbol)
                if spot is None:
                    self.logger.debug(f"[TRADE_SELECTOR] No spot for {symbol}, skipping")
                    continue

                vix = await self._load_vix() or 15.0
                gex_by_strike = await self._load_gex_by_strike(symbol)
                bias_lfi = await self._load_bias_lfi(symbol)

                # Time-based checks (use fractional hour for session detection)
                now = datetime.now()
                current_hour = now.hour + now.minute / 60.0

                # Session info
                session, session_info = self._get_session(current_hour)

                # Regime info (playbook-based)
                regime, special = self._get_vix_regime(vix, int(current_hour))

                # Time decay factor for scoring adjustments
                decay_factor = self._get_time_decay_factor(session, regime)

                # Expected Move calculations
                em_0dte = self._calculate_expected_move(spot, vix, 0)
                em_1dte = self._calculate_expected_move(spot, vix, 1)
                em_breach = self._estimate_em_breach_probability(regime, session, vix)

                # Gamma scalp window detection
                gamma_scalp_active, gamma_scalp_window = self._is_gamma_scalp_window(current_hour, regime)

                all_scores: List[Dict[str, Any]] = []
                gamma_scalp_candidates: List[Dict[str, Any]] = []  # Separate list for gamma scalp
                filtered_count = 0  # Track tiles rejected by 5% filter

                # Load unified heatmap
                heatmap = await self._load_heatmap(symbol)
                if not heatmap:
                    self.logger.debug(f"[TRADE_SELECTOR] No heatmap for {symbol}")
                    continue

                tiles = heatmap.get("tiles", {})

                # Build debit lookup for convexity calculation
                # Group debits by strike for gradient calculation
                debits_by_strike: Dict[float, Dict[str, float]] = {}

                # First pass: collect all debits by strike
                for tile_key, tile_data in tiles.items():
                    if not isinstance(tile_data, dict):
                        continue

                    # Parse tile key: strategy:dte:width:strike
                    parts = tile_key.split(":")
                    if len(parts) != 4:
                        continue

                    tile_strategy = parts[0]
                    if tile_strategy != "butterfly":
                        continue  # Only score butterflies for now

                    try:
                        strike = float(parts[3])
                        width = int(parts[2])
                    except (ValueError, IndexError):
                        continue

                    # Collect debits for both call and put sides
                    for side in ["call", "put"]:
                        side_data = tile_data.get(side, {})
                        debit = side_data.get("debit")
                        if debit is not None and debit > 0:
                            if strike not in debits_by_strike:
                                debits_by_strike[strike] = {}
                            debits_by_strike[strike][f"{width}_{side}"] = debit

                # Second pass: score all butterfly tiles
                for tile_key, tile_data in tiles.items():
                    if not isinstance(tile_data, dict):
                        continue

                    # Parse tile key: strategy:dte:width:strike
                    parts = tile_key.split(":")
                    if len(parts) != 4:
                        continue

                    tile_strategy = parts[0]
                    if tile_strategy != "butterfly":
                        continue

                    try:
                        dte = int(parts[1])
                        width = int(parts[2])
                        strike = float(parts[3])
                    except (ValueError, IndexError):
                        continue

                    # Process both call and put sides
                    for side in ["call", "put"]:
                        side_data = tile_data.get(side, {})
                        debit = side_data.get("debit")

                        if debit is None or debit <= 0:
                            continue

                        # ==============================================
                        # HARD FILTER: 5% debit/width rule
                        # Ensures extreme asymmetry (e.g., 30-wide max $1.50)
                        # ==============================================
                        if not self._passes_debit_filter(width, debit):
                            filtered_count += 1
                            continue

                        # Get all debits at this strike for convexity calculation
                        all_debits_for_strike = debits_by_strike.get(strike, {})

                        # Calculate scores
                        r2r_score = self._score_r2r(width, debit)
                        convexity_score = self._score_convexity(
                            strike, width, debit, all_debits_for_strike, gex_by_strike
                        )
                        width_fit_score = self._score_width_fit(
                            width, dte, regime, special, decay_factor, session, session_info
                        )
                        gamma_alignment_score = self._score_gamma_alignment(
                            strike, width, side, spot, gex_by_strike, bias_lfi
                        )

                        composite = self._calculate_composite_score(
                            r2r_score, convexity_score, width_fit_score, gamma_alignment_score
                        )

                        confidence = self._calculate_confidence(
                            has_gex=bool(gex_by_strike),
                            has_bias_lfi=bool(bias_lfi),
                            debit=debit,
                        )

                        # Use tile key with side appended
                        scored_tile_key = f"{tile_key}:{side}"

                        # Calculate derived values
                        max_profit = width - debit
                        max_loss = debit
                        r2r_ratio = max_profit / debit if debit > 0 else 0
                        debit_pct = (debit / width) * 100  # Debit as % of width
                        distance_to_spot = strike - spot

                        gamma_magnet = bias_lfi.get("max_net_gex_strike") if bias_lfi else None
                        distance_to_gamma_magnet = (
                            strike - gamma_magnet if gamma_magnet is not None else None
                        )

                        all_scores.append({
                            "tile_key": scored_tile_key,
                            "composite": round(composite, 1),
                            "confidence": round(confidence, 2),
                            "components": {
                                "r2r": round(r2r_score, 1),
                                "convexity": round(convexity_score, 1),
                                "width_fit": round(width_fit_score, 1),
                                "gamma_alignment": round(gamma_alignment_score, 1),
                            },
                            # Tile details
                            "strategy": "butterfly",
                            "side": side,
                            "strike": strike,
                            "width": width,
                            "dte": dte,
                            "debit": round(debit, 2),
                            "debit_pct": round(debit_pct, 1),  # New: shows asymmetry
                            # Computed
                            "max_profit": round(max_profit, 2),
                            "max_loss": round(max_loss, 2),
                            "r2r_ratio": round(r2r_ratio, 2),
                            "distance_to_spot": round(distance_to_spot, 1),
                            "distance_to_gamma_magnet": round(distance_to_gamma_magnet, 1) if distance_to_gamma_magnet is not None else None,
                        })

                        # ==============================================
                        # GAMMA SCALP MODE: Score 0DTE near-ATM flies
                        # ==============================================
                        if gamma_scalp_active and dte == 0:
                            gs_score, gs_details = self._score_gamma_scalp(
                                strike, width, debit, spot, regime, gamma_scalp_window
                            )
                            if gs_details.get("is_candidate"):
                                gamma_scalp_candidates.append({
                                    "tile_key": scored_tile_key,
                                    "gamma_scalp_score": gs_score,
                                    "gamma_scalp_details": gs_details,
                                    "strategy": "gamma_scalp",
                                    "side": side,
                                    "strike": strike,
                                    "width": width,
                                    "dte": dte,
                                    "debit": round(debit, 2),
                                    "debit_pct": round(debit_pct, 1),
                                    "max_profit": round(max_profit, 2),
                                    "max_loss": round(max_loss, 2),
                                    "r2r_ratio": round(r2r_ratio, 2),
                                    "distance_to_spot": round(distance_to_spot, 1),
                                })

                # Sort by composite score descending
                all_scores.sort(key=lambda x: x["composite"], reverse=True)

                # Sort gamma scalp candidates by score
                gamma_scalp_candidates.sort(key=lambda x: x["gamma_scalp_score"], reverse=True)

                # Build scores lookup by tile_key
                scores_dict = {s["tile_key"]: {
                    "tile_key": s["tile_key"],
                    "composite": s["composite"],
                    "confidence": s["confidence"],
                    "components": s["components"],
                } for s in all_scores}

                # Top N recommendations with rank and convexity analysis
                recommendations = []
                for rank, score in enumerate(all_scores[:self.top_n], 1):
                    # Calculate convexity opportunity for this trade
                    convexity_opp = self._calculate_convexity_opportunity(
                        em_breach["breach_probability"],
                        score["r2r_ratio"],
                        score["dte"],
                    )

                    recommendations.append({
                        "rank": rank,
                        "tile_key": score["tile_key"],
                        "score": {
                            "tile_key": score["tile_key"],
                            "composite": score["composite"],
                            "confidence": score["confidence"],
                            "components": score["components"],
                        },
                        "strategy": score["strategy"],
                        "side": score["side"],
                        "strike": score["strike"],
                        "width": score["width"],
                        "dte": score["dte"],
                        "debit": score["debit"],
                        "debit_pct": score["debit_pct"],  # Debit as % of width
                        "max_profit": score["max_profit"],
                        "max_loss": score["max_loss"],
                        "r2r_ratio": score["r2r_ratio"],
                        "distance_to_spot": score["distance_to_spot"],
                        "distance_to_gamma_magnet": score["distance_to_gamma_magnet"],
                        # Convexity opportunity analysis
                        "convexity": convexity_opp,
                    })

                # Build indicator snapshot for market context
                ideal_width = self._get_ideal_width_range(regime, special)
                ideal_dte = self._get_ideal_dte_range(regime, special)

                indicator_snapshot = {
                    "spot": spot,
                    "vix": vix,
                    "vix_regime": regime,
                    "vix_special": special,
                    # Session info
                    "session": session,
                    "session_info": session_info,
                    # Expected Move data
                    "expected_move_0dte": em_0dte,
                    "expected_move_1dte": em_1dte,
                    "em_breach_probability": em_breach["breach_probability"],
                    "em_breach_pct": em_breach["breach_pct"],
                    "em_breach_likelihood": em_breach["likelihood"],
                    # Playbook guidance
                    "ideal_width_min": ideal_width[0],
                    "ideal_width_max": ideal_width[1],
                    "ideal_dte_min": ideal_dte[0],
                    "ideal_dte_max": ideal_dte[1],
                    "decay_factor": round(decay_factor, 2),
                    "max_debit_pct": self.MAX_DEBIT_PCT * 100,  # 5%
                    # GEX data
                    "gamma_magnet": bias_lfi.get("max_net_gex_strike") if bias_lfi else None,
                    "zero_gamma": bias_lfi.get("gex_flip_level") if bias_lfi else None,
                    "flip_above": bias_lfi.get("flip_above") if bias_lfi else None,
                    "flip_below": bias_lfi.get("flip_below") if bias_lfi else None,
                    "directional_strength": bias_lfi.get("directional_strength") if bias_lfi else None,
                    "lfi_score": bias_lfi.get("lfi_score") if bias_lfi else None,
                    "market_mode_score": bias_lfi.get("market_mode_score") if bias_lfi else None,
                    "total_net_gex": bias_lfi.get("total_net_gex") if bias_lfi else None,
                    "max_call_gex_strike": bias_lfi.get("max_call_gex_strike") if bias_lfi else None,
                    "max_put_gex_strike": bias_lfi.get("max_put_gex_strike") if bias_lfi else None,
                }

                # Build model
                ts = time.time()
                model = {
                    "ts": ts,
                    "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
                    "symbol": symbol,
                    "spot": spot,
                    "vix": vix,
                    "vix_regime": regime,
                    "vix_special": special,
                    # Playbook context
                    "playbook": {
                        "regime": regime,
                        "session": session,
                        "ideal_width": f"{ideal_width[0]}-{ideal_width[1]}",
                        "ideal_dte": f"{ideal_dte[0]}-{ideal_dte[1]}",
                        "max_debit_pct": self.MAX_DEBIT_PCT * 100,
                        "decay_factor": round(decay_factor, 2),
                        "entry_optimal": session_info.get("is_entry_optimal", False),
                        "exercise_window": session_info.get("is_exercise_window", False),
                        "outlier_zone": session_info.get("is_outlier_zone", False),
                    },
                    # Expected Move analysis
                    "expected_move": {
                        "em_0dte": em_0dte,
                        "em_1dte": em_1dte,
                        "em_upper": round(spot + em_0dte, 2),
                        "em_lower": round(spot - em_0dte, 2),
                        "breach": em_breach,
                        "payoff_zones": self.PAYOFF_ZONES,
                    },
                    # Gamma Scalp mode
                    "gamma_scalp": {
                        "active": gamma_scalp_active,
                        "window": gamma_scalp_window,
                        "candidates": gamma_scalp_candidates[:5],  # Top 5 gamma scalp candidates
                        "total_candidates": len(gamma_scalp_candidates),
                    },
                    "gamma_magnet": bias_lfi.get("max_net_gex_strike") if bias_lfi else None,
                    "zero_gamma": bias_lfi.get("gex_flip_level") if bias_lfi else None,
                    "indicator_snapshot": indicator_snapshot,
                    "scores": scores_dict,
                    "recommendations": recommendations,
                    "total_scored": len(all_scores),
                    "filtered_by_debit_rule": filtered_count,
                }

                # Publish to Redis
                await r.set(
                    f"massive:selector:model:{symbol}:latest",
                    json.dumps(model),
                    ex=self.model_ttl_sec,
                )

                self.logger.debug(
                    f"[TRADE_SELECTOR] {symbol} regime={regime} session={session} "
                    f"width={ideal_width[0]}-{ideal_width[1]} dte={ideal_dte[0]}-{ideal_dte[1]} "
                    f"scored={len(all_scores)} filtered={filtered_count}",
                    emoji="🎯",
                )

            # Record analytics
            latency_ms = int((time.monotonic() - t_start) * 1000)
            await r.hincrby(self.ANALYTICS_KEY, f"{self.BUILDER_NAME}:runs", 1)
            await r.hset(self.ANALYTICS_KEY, f"{self.BUILDER_NAME}:latency_last_ms", latency_ms)

            self.logger.info(
                f"[TRADE_SELECTOR] symbols={len(self.symbols)} latency={latency_ms}ms",
                emoji="🎯",
            )

        except Exception as e:
            self.logger.error(f"[TRADE_SELECTOR ERROR] {e}", emoji="💥")
            await r.hincrby(self.ANALYTICS_KEY, f"{self.BUILDER_NAME}:errors", 1)
            raise

    async def run(self, stop_event: asyncio.Event) -> None:
        """Main run loop."""
        self.logger.info("[TRADE_SELECTOR START] running", emoji="🎯")
        try:
            while not stop_event.is_set():
                t0 = time.monotonic()
                await self._build_once()
                dt = time.monotonic() - t0
                await asyncio.sleep(max(0.0, self.interval_sec - dt))
        finally:
            self.logger.info("[TRADE_SELECTOR STOP] halted", emoji="🛑")
