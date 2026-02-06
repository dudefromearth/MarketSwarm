#!/usr/bin/env python3
# services/massive/intel/model_builders/trade_selector.py
"""
Trade Selector Model Builder

Finds CONVEX pricing anomalies - trades significantly cheaper than nearby
alternatives without sacrificing optionality. VIX determines environment,
but convexity is always the target.

Campaigns:
- 0-2 DTE Tactical: 3-7 trades/week, R2R 9-18, debit 7-10% of width
- Convex Stack (3-5 DTE): 2 trades/week overlapping, R2R 15-30, debit 5-7%
- Sigma Drift (5-10 DTE): 6/month, R2R 20-50, debit 3-5%

Edge Cases (part of 0-2 DTE):
- TimeWarp: VIX ≤17, 1-2 DTE, captures overnight moves + slower decay
- Batman: VIX 24+, dual fly (put below + call above spot), 30-50+ wide
- Gamma Scalp: Late day 0DTE, 15-25 wide, near ATM, structural squeeze

Scoring Components:
1. Convexity Score (40%) - PRIMARY: cheaper than nearby alternatives
2. R:R Score (25%) - Relative to DTE expectations
3. Width Fit Score (20%) - VIX regime alignment
4. Gamma Alignment Score (15%) - GEX structure

Hard Filter: Debit ≤ 10% of width (minimum 1:9 R2R)

Publishes to: massive:selector:model:{symbol}:latest
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import time
import uuid
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from redis.asyncio import Redis

# ML Feedback Loop integration
try:
    import sys
    import os
    # Add services directory to path for ml_feedback import
    _services_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    if _services_dir not in sys.path:
        sys.path.insert(0, _services_dir)

    from ml_feedback import (
        InferenceEngine,
        FeatureExtractor,
        DecisionLogger,
        CircuitBreaker,
        MLConfig,
    )
    from ml_feedback.feature_extractor import MarketSnapshot, TradeIdea
    ML_FEEDBACK_AVAILABLE = True
except ImportError as e:
    ML_FEEDBACK_AVAILABLE = False
    # Store the import error for debugging
    _ML_IMPORT_ERROR = str(e)


class TradeSelectorModelBuilder:
    """
    Calculates composite scores for heatmap tiles and publishes top recommendations.
    """

    ANALYTICS_KEY = "massive:model:analytics"
    BUILDER_NAME = "trade_selector"

    # Score weights - Convexity is PRIMARY
    WEIGHT_CONVEXITY = 0.40      # PRIMARY: cheaper than nearby alternatives
    WEIGHT_R2R = 0.25            # R2R relative to DTE expectations
    WEIGHT_WIDTH_FIT = 0.20      # VIX regime alignment
    WEIGHT_GAMMA_ALIGNMENT = 0.15  # GEX structure

    # ==========================================================================
    # Big Ass Fly Playbook Constants
    # ==========================================================================

    # Hard filter: debit must be ≤ this percentage of width
    # 10% = 1:9 R2R (e.g., 30-wide max debit $3.00)
    # Best trades often at 5% (1:19 R2R) but 10% is the hard cutoff
    MAX_DEBIT_PCT = 0.10

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

    # TimeWarp: Low VIX strategy triggered by TWO converging factors:
    # 1. Accelerated premium decay (0DTE premium evaporates too fast)
    # 2. Compressed intraday movement / overnight gap dominance
    # Solution: Go out 1-2 DTE to capture slower decay + overnight Globex moves
    TIMEWARP_VIX_THRESHOLD = 17   # VIX ≤ 17 for TimeWarp consideration
    TIMEWARP_WIDTH = (10, 20)     # Narrower flies for TimeWarp strategy
    TIMEWARP_DTE = (1, 2)         # 1-2 DTE to capture overnight moves

    # ==========================================================================
    # Batman: Dual fly structure (put below + call above spot)
    # ==========================================================================
    # Becomes more attractive as VIX rises from Goldilocks 2 (24+) into Chaos
    # Structure: Put fly BELOW spot + Call fly ABOVE spot
    # Can be equal widths or skewed based on gamma/Volume Profile structure
    BATMAN_VIX_THRESHOLD = 24     # VIX 24+ for Batman consideration
    BATMAN_WIDTH = (30, 100)      # 30-50+ wide, wider usually better
    BATMAN_DTE = (0, 2)           # 0-2 DTE

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
    # Lower VIX = wider window (gamma already elevated, premium decayed)
    # Higher VIX = narrower window (gamma doesn't spike until very late)
    GAMMA_SCALP_WINDOWS = {
        "zombieland": (12.5, 16.0),   # 12:30 PM - 4:00 PM (widest window in low vol)
        "goldilocks_1": (14.0, 16.0), # 2:00 PM - 4:00 PM
        "goldilocks_2": (15.0, 16.0), # 3:00 PM - 4:00 PM (tighter)
        "chaos": (15.0, 16.0),        # 3:00 PM - 4:00 PM (tight window, gamma late)
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

    # R:R expectations by DTE (campaign-based)
    # 0-2 DTE Tactical: R2R 9-18, debit 7-10% of width
    # Convex Stack (3-5 DTE): R2R 15-30, debit 5-7% of width
    # Sigma Drift (5-10 DTE): R2R 20-50, debit 3-5% of width
    R2R_EXPECTATIONS = {
        0: {"typical": (9, 12), "max": (15, 18), "campaign": "0dte_tactical"},
        1: {"typical": (10, 14), "max": (16, 20), "campaign": "0dte_tactical"},
        2: {"typical": (12, 16), "max": (18, 24), "campaign": "0dte_tactical"},
        3: {"typical": (15, 22), "max": (25, 30), "campaign": "convex_stack"},
        4: {"typical": (18, 25), "max": (28, 35), "campaign": "convex_stack"},
        5: {"typical": (20, 30), "max": (30, 40), "campaign": "convex_stack"},
        6: {"typical": (22, 35), "max": (35, 45), "campaign": "sigma_drift"},
        7: {"typical": (25, 38), "max": (38, 48), "campaign": "sigma_drift"},
        8: {"typical": (28, 42), "max": (42, 52), "campaign": "sigma_drift"},
        9: {"typical": (30, 45), "max": (45, 55), "campaign": "sigma_drift"},
        10: {"typical": (35, 50), "max": (50, 60), "campaign": "sigma_drift"},
    }

    # Campaign definitions
    CAMPAIGNS = {
        "0dte_tactical": {
            "dte_range": (0, 2),
            "r2r_typical": (9, 18),
            "debit_pct_range": (0.07, 0.10),  # 7-10% of width
            "frequency": "3-7/week",
        },
        "convex_stack": {
            "dte_range": (3, 5),
            "r2r_typical": (15, 30),
            "debit_pct_range": (0.05, 0.07),  # 5-7% of width
            "frequency": "2/week overlapping",
        },
        "sigma_drift": {
            "dte_range": (5, 10),
            "r2r_typical": (20, 50),
            "debit_pct_range": (0.03, 0.05),  # 3-5% of width
            "frequency": "6/month",
        },
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

        # ------------------------------------------------------------------
        # Trade Idea Tracking (P&L instrumentation)
        # ------------------------------------------------------------------
        self.tracking_enabled = config.get("MASSIVE_SELECTOR_TRACKING", "true").lower() == "true"

        # In-memory tracking of active trades
        # Key: unique trade ID (f"{symbol}:{tile_key}:{entry_ts}")
        # Value: dict with trade details and max profit tracking
        self._tracked_trades: Dict[str, Dict[str, Any]] = {}

        # Previous top 10 for detecting new entries
        self._prev_top10: Dict[str, set] = {}  # symbol -> set of tile_keys

        # Redis keys for persistence
        self.TRACKING_ACTIVE_KEY = "massive:selector:tracking:active"
        self.TRACKING_HISTORY_KEY = "massive:selector:tracking:history"
        self.TRACKING_STATS_KEY = "massive:selector:tracking:stats"
        self.TRACKING_TOTALS_KEY = "massive:selector:tracking:totals"

        # Journal API for persistent tracking storage
        self.journal_api_url = config.get("JOURNAL_API_URL", "http://localhost:3002")
        self._http_session = None  # Lazy init aiohttp session

        # Current active params version (for tracking which params generated the idea)
        self._active_params_version: Optional[int] = None

        # ------------------------------------------------------------------
        # ML Feedback Loop Integration
        # ------------------------------------------------------------------
        self.ml_enabled = config.get("MASSIVE_SELECTOR_ML_ENABLED", "false").lower() == "true"
        self.ml_weight = float(config.get("MASSIVE_SELECTOR_ML_WEIGHT", "0.0"))  # 0 = shadow mode
        self._ml_engine = None
        self._feature_extractor = None
        self._decision_logger = None
        self._circuit_breaker = None
        self._ml_context_id = None  # Cached market context ID

        if self.ml_enabled and ML_FEEDBACK_AVAILABLE:
            self.logger.info("[TRADE_SELECTOR] ML Feedback Loop enabled", emoji="🤖")
        elif self.ml_enabled and not ML_FEEDBACK_AVAILABLE:
            self.logger.warn("[TRADE_SELECTOR] ML Feedback requested but module not available", emoji="⚠️")
            self.ml_enabled = False

        self.logger.info(
            f"[TRADE_SELECTOR INIT] symbols={self.symbols} interval={self.interval_sec}s top_n={self.top_n} tracking={self.tracking_enabled} ml={self.ml_enabled}",
            emoji="🎯",
        )

    async def _redis_conn(self) -> Redis:
        if not self._redis:
            self._redis = Redis.from_url(self.market_redis_url, decode_responses=True)
        return self._redis

    # ------------------------------------------------------------------
    # ML Feedback Loop
    # ------------------------------------------------------------------

    async def _init_ml_engine(self) -> None:
        """Initialize ML components if enabled."""
        if not self.ml_enabled or not ML_FEEDBACK_AVAILABLE:
            return

        if self._ml_engine is not None:
            return  # Already initialized

        try:
            self._feature_extractor = FeatureExtractor()
            self._ml_engine = InferenceEngine(journal_api_url=self.journal_api_url)
            self._circuit_breaker = CircuitBreaker()

            # Load models
            await self._ml_engine.load_models()

            # Log model loading status
            if self._ml_engine._fast_model:
                self.logger.info(
                    f"[TRADE_SELECTOR] ML Engine initialized with model v{self._ml_engine._fast_model.version}",
                    emoji="🤖"
                )
            else:
                self.logger.warn("[TRADE_SELECTOR] ML Engine initialized but no model loaded", emoji="⚠️")
        except Exception as e:
            self.logger.error(f"[TRADE_SELECTOR] ML Engine init failed: {e}", emoji="💥")
            self.ml_enabled = False

    def _cache_ml_context(
        self,
        spot: float,
        vix: float,
        vix3m: Optional[float],
        day_high: Optional[float],
        day_low: Optional[float],
        gex_context: Optional[Dict[str, Any]],
        bias_lfi: Optional[Dict[str, Any]],
    ) -> str:
        """Cache market context for ML scoring (call once per build cycle)."""
        if not self.ml_enabled or not self._ml_engine:
            return ""

        # Create market snapshot
        snapshot = MarketSnapshot(
            spot=spot,
            vix=vix,
            vix3m=vix3m or 0.0,
            day_high=day_high,
            day_low=day_low,
            gex_total=gex_context.get("total_net_gex") if gex_context else None,
            gex_call_wall=gex_context.get("call_wall") if gex_context else None,
            gex_put_wall=gex_context.get("put_wall") if gex_context else None,
            gex_gamma_flip=gex_context.get("gamma_flip") if gex_context else None,
            market_mode=bias_lfi.get("market_mode") if bias_lfi else None,
            bias_lfi=bias_lfi.get("lfi_score") if bias_lfi else None,
            bias_direction=bias_lfi.get("direction") if bias_lfi else None,
        )

        # Generate unique context ID for this snapshot
        context_id = f"ctx_{int(time.time() * 1000)}"

        # Cache the context
        self._ml_engine.cache_market_context(context_id, snapshot)
        self._ml_context_id = context_id

        return context_id

    async def _get_ml_score(
        self,
        idea_id: str,
        strategy: str,
        side: str,
        strike: float,
        width: int,
        dte: int,
        debit: float,
        original_score: float,
    ) -> Tuple[Optional[float], Optional[float]]:
        """Get ML score for a trade idea.

        Returns (ml_score, final_blended_score).
        Returns (None, original_score) if ML unavailable.
        """
        if not self.ml_enabled or not self._ml_engine or not self._ml_context_id:
            return None, original_score

        try:
            # Check circuit breakers first
            breaker_status = await self._circuit_breaker.check_all_breakers()
            if not breaker_status.allow_trade or breaker_status.action == 'rules_only':
                return None, original_score

            # Create trade idea
            idea = TradeIdea(
                id=idea_id,
                symbol="SPX",  # TODO: pass actual symbol
                strategy=strategy,
                side=side,
                strike=strike,
                width=width,
                dte=dte,
                debit=debit,
                score=original_score,
            )

            # Get fast path ML score
            result = await self._ml_engine.score_idea_fast(
                idea=idea,
                market_context_id=self._ml_context_id,
            )

            if result.ml_score is None:
                return None, original_score

            # Blend scores based on configured weight
            final_score = original_score * (1 - self.ml_weight) + result.ml_score * self.ml_weight

            return result.ml_score, final_score

        except Exception as e:
            self.logger.debug(f"[TRADE_SELECTOR] ML scoring error: {e}")
            return None, original_score

    async def _log_ml_decision(
        self,
        idea_id: str,
        original_score: float,
        ml_score: Optional[float],
        final_score: float,
        feature_snapshot_id: int = 0,
        experiment_id: Optional[int] = None,
        experiment_arm: Optional[str] = None,
    ) -> None:
        """Log an ML decision for feedback loop."""
        if not self.tracking_enabled:
            return

        try:
            # Log to Journal API
            session = await self._get_http_session()
            async with session.post(
                f"{self.journal_api_url}/api/internal/ml/decisions",
                json={
                    "idea_id": idea_id,
                    "selector_params_version": self._active_params_version or 1,
                    "feature_snapshot_id": feature_snapshot_id,
                    "original_score": original_score,
                    "ml_score": ml_score,
                    "final_score": final_score,
                    "experiment_id": experiment_id,
                    "experiment_arm": experiment_arm,
                    "action_taken": "ranked",
                },
            ) as resp:
                if resp.status == 201:
                    self.logger.info(f"[TRADE_SELECTOR] ML decision logged successfully")
                else:
                    text = await resp.text()
                    self.logger.warning(f"[TRADE_SELECTOR] ML decision log failed: {resp.status} - {text[:100]}")
        except Exception as e:
            self.logger.warning(f"[TRADE_SELECTOR] ML decision log error: {e}")

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
        """Load current VIX value from spot worker."""
        r = await self._redis_conn()
        # Primary source: live VIX spot from massive spot worker
        raw = await r.get("massive:model:spot:I:VIX")
        if raw:
            try:
                data = json.loads(raw)
                return float(data.get("value"))
            except (json.JSONDecodeError, TypeError, KeyError):
                pass
        # Fallback: try vexy_ai signals
        raw = await r.get("vexy_ai:signals:latest")
        if raw:
            try:
                data = json.loads(raw)
                return float(data.get("vix") or data.get("VIX"))
            except (json.JSONDecodeError, TypeError, KeyError):
                pass
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

    def _get_vix_regime(self, vix: float, current_hour: float) -> Tuple[str, Optional[str]]:
        """
        Get VIX regime and special condition/strategy based on playbook.
        Returns (regime, special_condition).

        Regimes (based on VIX level):
        - chaos: VIX ≥ 32 (high volatility, slow decay, wide flies)
        - goldilocks_2: VIX 23-32 (elevated vol)
        - goldilocks_1: VIX 17-23 (normal vol)
        - zombieland: VIX < 17 (low vol, fast decay)

        Special conditions/strategies (edge cases, not regimes):
        - batman: VIX ≥ 24 (Goldilocks 2 into Chaos) - frequency increases with VIX
        - timewarp: VIX ≤ 17 - accelerated decay + overnight gap dominance
        - gamma_scalp: Late session opportunity - window depends on VIX regime
        """
        # Determine regime first
        if vix >= self.VIX_CHAOS_CUT:
            regime = "chaos"
        elif vix >= self.VIX_GOLD2_CUT:
            regime = "goldilocks_2"
        elif vix >= self.VIX_GOLD1_CUT:
            regime = "goldilocks_1"
        else:
            regime = "zombieland"

        # Determine special condition/edge case
        # Note: Multiple edge cases can be relevant, we return the most relevant one
        special = None

        # Batman: VIX 24+ (becomes more attractive as VIX rises)
        if vix >= self.BATMAN_VIX_THRESHOLD:
            special = "batman"

        # TimeWarp: Low VIX (≤17) with accelerated decay
        elif vix <= self.TIMEWARP_VIX_THRESHOLD:
            special = "timewarp"

        # Gamma Scalp: Check if in time window for this regime
        if special != "batman":  # Batman takes priority over gamma scalp
            gamma_window = self.GAMMA_SCALP_WINDOWS.get(regime)
            if gamma_window:
                start_hour, end_hour = gamma_window
                if start_hour <= current_hour <= end_hour:
                    # Gamma scalp is available, but don't override timewarp
                    # Both can be considered - timewarp for 1-2 DTE, gamma scalp for 0DTE
                    if special != "timewarp":
                        special = "gamma_scalp"

        return regime, special

    def _get_campaign(self, dte: int) -> str:
        """
        Determine which campaign a trade belongs to based on DTE.

        Campaigns:
        - 0dte_tactical: 0-2 DTE (includes TimeWarp, Batman, Gamma Scalp)
        - convex_stack: 3-5 DTE
        - sigma_drift: 5-10 DTE (overlaps with convex_stack at 5)
        """
        if dte <= 2:
            return "0dte_tactical"
        elif dte <= 5:
            return "convex_stack"
        else:
            return "sigma_drift"

    def _get_edge_cases(self, vix: float, current_hour: float, dte: int, regime: str) -> List[str]:
        """
        Get all applicable edge case strategies for current conditions.
        A trade might qualify for multiple edge cases.
        """
        edge_cases = []

        # Batman: VIX 24+ and 0-2 DTE
        if vix >= self.BATMAN_VIX_THRESHOLD and dte <= 2:
            edge_cases.append("batman")

        # TimeWarp: VIX ≤ 17 and 1-2 DTE
        if vix <= self.TIMEWARP_VIX_THRESHOLD and 1 <= dte <= 2:
            edge_cases.append("timewarp")

        # Gamma Scalp: 0DTE and in time window
        if dte == 0:
            gamma_window = self.GAMMA_SCALP_WINDOWS.get(regime)
            if gamma_window:
                start_hour, end_hour = gamma_window
                if start_hour <= current_hour <= end_hour:
                    edge_cases.append("gamma_scalp")

        return edge_cases

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
        Hard filter: debit must be ≤ 10% of width for minimum 1:9 R2R.
        E.g., 30-wide fly max debit = $3.00, 20-wide max = $2.00
        Best trades often at 5% (1:19 R2R) but this is the hard cutoff.
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

    def _score_r2r(self, width: int, debit: float, dte: int = 0) -> float:
        """
        Calculate R:R score (0-100) RELATIVE to DTE expectations.

        R2R expectations by campaign:
        - 0-2 DTE Tactical: R2R 9-18, debit 7-10% of width
        - Convex Stack (3-5 DTE): R2R 15-30, debit 5-7% of width
        - Sigma Drift (5-10 DTE): R2R 20-50, debit 3-5% of width

        Score is based on how the trade compares to typical/max expectations
        for its DTE, not absolute R2R values.
        """
        if debit <= 0.10:
            return 0.0  # Won't fill

        r2r = (width - debit) / debit
        if r2r <= 0:
            return 0.0

        # Get expectations for this DTE
        expectations = self._get_r2r_expectations(dte)
        typical_low, typical_high = expectations["typical"]
        max_low, max_high = expectations["max"]

        # Score relative to expectations
        if r2r >= max_high:
            # Exceptional - above max expectations
            score = 95.0
        elif r2r >= max_low:
            # Excellent - in the max range
            score = 85.0 + ((r2r - max_low) / (max_high - max_low)) * 10
        elif r2r >= typical_high:
            # Good - above typical
            score = 75.0 + ((r2r - typical_high) / (max_low - typical_high)) * 10
        elif r2r >= typical_low:
            # Acceptable - in typical range
            score = 60.0 + ((r2r - typical_low) / (typical_high - typical_low)) * 15
        elif r2r >= typical_low * 0.8:
            # Below typical but close
            score = 45.0 + ((r2r - typical_low * 0.8) / (typical_low * 0.2)) * 15
        else:
            # Well below expectations for this DTE
            score = max(20.0, 45.0 * (r2r / (typical_low * 0.8)))

        # Penalty for likely illiquid
        if debit < 0.50:
            score *= (debit / 0.50)

        return max(0, min(95, score))

    def _score_convexity(
        self,
        strike: float,
        width: int,
        debit: float,
        all_debits: Dict[str, float],
        gex_by_strike: Dict[float, Dict[str, float]],
        all_tiles_debits: Optional[Dict[str, float]] = None,
    ) -> float:
        """
        Calculate convexity score (0-100).

        CONVEXITY is the core metric: finding trades that are significantly
        cheaper than nearby alternatives without sacrificing optionality.
        This is the whole point of the heatmap - to find pricing anomalies.

        Three sub-components:
        - Local Price Advantage (50%): How much cheaper vs same-width flies at nearby strikes
        - Neighborhood Cheapness (30%): Is this a local minimum in the debit surface?
        - Width Efficiency (20%): R2R quality relative to width
        """
        # Local Price Advantage (50%) - compare same-width flies at nearby strikes
        # This is the PRIMARY convexity signal
        local_advantage_score = 50.0
        same_width_debits = []

        # Check same-width butterflies at adjacent strikes (+/- 5, 10, 15, 20)
        if all_tiles_debits:
            for adj in [-20, -15, -10, -5, 5, 10, 15, 20]:
                adj_strike = strike + adj
                # Key format: width_side (e.g., "30_call")
                for side_key in [f"{width}_call", f"{width}_put"]:
                    lookup_key = f"{adj_strike}:{side_key}"
                    if lookup_key in all_tiles_debits:
                        same_width_debits.append(all_tiles_debits[lookup_key])

        # Fallback to old method if no same-width data
        if not same_width_debits:
            for adj in [-5, 5, -10, 10]:
                adj_strike = strike + adj
                adj_key = str(int(adj_strike))
                if adj_key in all_debits:
                    same_width_debits.append(all_debits[adj_key])

        if same_width_debits and debit > 0:
            avg_neighbors = sum(same_width_debits) / len(same_width_debits)
            min_neighbor = min(same_width_debits)
            max_neighbor = max(same_width_debits)

            if avg_neighbors > 0:
                # How much cheaper are we than the average neighbor?
                pct_cheaper = ((avg_neighbors - debit) / avg_neighbors) * 100

                # Are we cheaper than ALL neighbors? (local minimum)
                is_local_min = debit < min_neighbor

                # Scoring:
                # - 10%+ cheaper than avg = excellent (85-95)
                # - 5-10% cheaper = good (70-85)
                # - 0-5% cheaper = okay (50-70)
                # - More expensive = penalty (30-50)
                # - Local minimum bonus: +10

                if pct_cheaper >= 15:
                    local_advantage_score = 95.0
                elif pct_cheaper >= 10:
                    local_advantage_score = 85.0 + (pct_cheaper - 10)
                elif pct_cheaper >= 5:
                    local_advantage_score = 70.0 + (pct_cheaper - 5) * 3
                elif pct_cheaper >= 0:
                    local_advantage_score = 50.0 + pct_cheaper * 4
                else:
                    # More expensive than neighbors - significant penalty
                    local_advantage_score = max(20.0, 50.0 + pct_cheaper * 2)

                # Bonus for being the local minimum
                if is_local_min:
                    local_advantage_score = min(98.0, local_advantage_score + 10)

        # Neighborhood Cheapness (30%) - statistical anomaly detection
        # Is this fly priced significantly below what nearby similar trades suggest?
        neighborhood_score = 50.0

        if same_width_debits and len(same_width_debits) >= 3 and debit > 0:
            avg = sum(same_width_debits) / len(same_width_debits)
            # Calculate standard deviation
            variance = sum((x - avg) ** 2 for x in same_width_debits) / len(same_width_debits)
            std_dev = math.sqrt(variance) if variance > 0 else 0.01

            # Z-score: how many std devs below average are we?
            z_score = (avg - debit) / std_dev if std_dev > 0.01 else 0

            # z >= 2 = significantly cheap (anomaly)
            # z >= 1 = noticeably cheap
            # z >= 0 = at or below average
            # z < 0 = more expensive than average

            if z_score >= 2.0:
                neighborhood_score = 95.0
            elif z_score >= 1.5:
                neighborhood_score = 85.0
            elif z_score >= 1.0:
                neighborhood_score = 75.0
            elif z_score >= 0.5:
                neighborhood_score = 65.0
            elif z_score >= 0:
                neighborhood_score = 55.0
            else:
                # More expensive than neighbors
                neighborhood_score = max(25.0, 50.0 + z_score * 15)

        # Width Efficiency (20%) - R2R scaled by debit percentage
        # Rewards trades that achieve high R2R at reasonable debit levels
        efficiency_score = 50.0
        if debit > 0:
            r2r = (width - debit) / debit
            debit_pct = (debit / width) * 100

            # Score R2R on log scale
            base_r2r_score = min(95, 30 * math.log2(r2r + 1))

            # Bonus for very low debit percentage (high asymmetry)
            # 3% debit = exceptional, 5% = great, 7% = good, 10% = acceptable
            if debit_pct <= 3:
                asymmetry_mult = 1.15
            elif debit_pct <= 5:
                asymmetry_mult = 1.10
            elif debit_pct <= 7:
                asymmetry_mult = 1.05
            else:
                asymmetry_mult = 1.0

            efficiency_score = min(95, base_r2r_score * asymmetry_mult)

        # Combine sub-components with convexity-focused weighting
        convexity = (
            local_advantage_score * 0.50 +  # Primary: cheaper than neighbors
            neighborhood_score * 0.30 +     # Statistical anomaly
            efficiency_score * 0.20         # R2R efficiency
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
    # Trade Idea Tracking (P&L Instrumentation)
    # ------------------------------------------------------------------

    def _calculate_butterfly_pnl(self, spot: float, strike: float, width: float, debit: float) -> float:
        """
        Calculate current P&L for a butterfly spread.

        Butterfly payoff at expiration:
        - Max profit at center strike = width - debit
        - Value decreases linearly as spot moves away from strike
        - Zero value when spot is beyond strike ± width

        For real-time tracking, we use intrinsic value approximation.
        """
        distance = abs(spot - strike)
        if distance >= width:
            # Spot is outside the butterfly wings - worthless
            intrinsic_value = 0.0
        else:
            # Butterfly has value: width - distance from center
            intrinsic_value = width - distance

        return intrinsic_value - debit

    def _generate_trade_id(self, symbol: str, tile_key: str, entry_ts: float) -> str:
        """Generate unique ID for a tracked trade."""
        return f"{symbol}:{tile_key}:{int(entry_ts)}"

    def _parse_expiration_from_dte(self, dte: int) -> datetime:
        """Calculate expiration datetime from DTE."""
        # Expiration is market close (4 PM ET) on the expiration day
        today = date.today()
        exp_date = today if dte == 0 else date(today.year, today.month, today.day + dte)
        # 4 PM ET = 21:00 UTC (during EST) or 20:00 UTC (during EDT)
        # Use 21:00 UTC as conservative estimate
        return datetime(exp_date.year, exp_date.month, exp_date.day, 21, 0, 0, tzinfo=timezone.utc)

    async def _track_new_entries(
        self,
        symbol: str,
        recommendations: List[Dict[str, Any]],
        spot: float,
        vix: float,
        regime: str,
        gex_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Detect new trades entering the top 10 and start tracking them.
        Only tracks trades that weren't in the previous top 10.
        """
        if not self.tracking_enabled:
            return

        r = await self._redis_conn()
        current_top10 = {rec["tile_key"] for rec in recommendations}
        prev_top10 = self._prev_top10.get(symbol, set())

        # Find new entries (in current but not in previous)
        new_entries = current_top10 - prev_top10

        now = time.time()
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat(timespec="seconds")

        # Time context
        entry_hour = now_dt.hour + now_dt.minute / 60.0  # e.g., 14.5 = 2:30 PM
        entry_day_of_week = now_dt.weekday()  # 0=Monday, 4=Friday

        # GEX context (extract from bias_lfi model if available)
        gex_flip = None
        gex_call_wall = None
        gex_put_wall = None
        if gex_context:
            gex_flip = gex_context.get("gamma_flip") or gex_context.get("gex_flip")
            gex_call_wall = gex_context.get("call_wall") or gex_context.get("call_resistance")
            gex_put_wall = gex_context.get("put_wall") or gex_context.get("put_support")

        for rec in recommendations:
            if rec["tile_key"] not in new_entries:
                continue

            trade_id = self._generate_trade_id(symbol, rec["tile_key"], now)

            # Calculate initial P&L
            initial_pnl = self._calculate_butterfly_pnl(
                spot, rec["strike"], rec["width"], rec["debit"]
            )

            # Build tracked trade record
            tracked = {
                "trade_id": trade_id,
                "symbol": symbol,
                "tile_key": rec["tile_key"],
                "entry_rank": rec["rank"],
                "entry_time": now_iso,
                "entry_ts": now,
                "entry_spot": spot,
                "entry_vix": vix,
                "entry_regime": regime,
                # Time context
                "entry_hour": round(entry_hour, 2),
                "entry_day_of_week": entry_day_of_week,
                # GEX context
                "entry_gex_flip": gex_flip,
                "entry_gex_call_wall": gex_call_wall,
                "entry_gex_put_wall": gex_put_wall,
                # Trade details
                "strategy": rec["strategy"],
                "side": rec["side"],
                "strike": rec["strike"],
                "width": rec["width"],
                "dte": rec["dte"],
                "debit": rec["debit"],
                "max_profit_theoretical": rec["width"] - rec["debit"],
                "r2r_predicted": rec["r2r_ratio"],
                "campaign": rec["campaign"],
                "edge_cases": rec["edge_cases"],
                # Expiration
                "expiration": self._parse_expiration_from_dte(rec["dte"]).isoformat(),
                # Real-time tracking
                "current_pnl": initial_pnl,
                "max_pnl": initial_pnl,
                "max_pnl_time": now_iso,
                "max_pnl_spot": spot,
                # Status
                "status": "active",
                "settled": False,
            }

            # Store in memory
            self._tracked_trades[trade_id] = tracked

            # Persist to Redis
            await r.hset(self.TRACKING_ACTIVE_KEY, trade_id, json.dumps(tracked))

            self.logger.info(
                f"[TRACKING] New entry: {rec['tile_key']} rank={rec['rank']} "
                f"strike={rec['strike']} width={rec['width']} debit={rec['debit']:.2f}",
                emoji="📊",
            )

        # Update previous top 10
        self._prev_top10[symbol] = current_top10

    async def _update_tracked_pnl(self, symbol: str, spot: float) -> None:
        """
        Update P&L for all active tracked trades.
        Records new max profit if current P&L exceeds previous max.
        """
        if not self.tracking_enabled:
            return

        r = await self._redis_conn()
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

        for trade_id, trade in list(self._tracked_trades.items()):
            if trade["symbol"] != symbol:
                continue
            if trade["status"] != "active":
                continue

            # Calculate current P&L
            current_pnl = self._calculate_butterfly_pnl(
                spot, trade["strike"], trade["width"], trade["debit"]
            )

            trade["current_pnl"] = current_pnl

            # Check for new max profit
            if current_pnl > trade["max_pnl"]:
                trade["max_pnl"] = current_pnl
                trade["max_pnl_time"] = now_iso
                trade["max_pnl_spot"] = spot

                self.logger.debug(
                    f"[TRACKING] New max P&L: {trade['tile_key']} "
                    f"pnl={current_pnl:.2f} spot={spot:.2f}",
                    emoji="📈",
                )

            # Update in Redis
            await r.hset(self.TRACKING_ACTIVE_KEY, trade_id, json.dumps(trade))

    async def _settle_expired_trades(self, symbol: str, spot: float) -> None:
        """
        Check for expired trades and record final settlement.
        """
        if not self.tracking_enabled:
            return

        r = await self._redis_conn()
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat(timespec="seconds")

        for trade_id, trade in list(self._tracked_trades.items()):
            if trade["symbol"] != symbol:
                continue
            if trade["status"] != "active":
                continue

            # Check if expired
            exp_time = datetime.fromisoformat(trade["expiration"])
            if now < exp_time:
                continue

            # Trade has expired - settle it
            final_pnl = self._calculate_butterfly_pnl(
                spot, trade["strike"], trade["width"], trade["debit"]
            )

            trade["status"] = "settled"
            trade["settled"] = True
            trade["settlement_time"] = now_iso
            trade["settlement_spot"] = spot
            trade["final_pnl"] = final_pnl
            trade["pnl_captured_pct"] = (
                (final_pnl / trade["max_pnl"] * 100) if trade["max_pnl"] > 0 else 0
            )

            # Calculate if trade was winner
            trade["is_winner"] = final_pnl > 0
            trade["r2r_achieved"] = (
                final_pnl / trade["debit"] if trade["debit"] > 0 else 0
            )

            # Move from active to history
            await r.hdel(self.TRACKING_ACTIVE_KEY, trade_id)
            await r.lpush(self.TRACKING_HISTORY_KEY, json.dumps(trade))

            # Update aggregate stats by entry rank
            rank = trade["entry_rank"]
            await r.hincrby(self.TRACKING_STATS_KEY, f"rank{rank}:count", 1)
            await r.hincrbyfloat(self.TRACKING_STATS_KEY, f"rank{rank}:total_pnl", final_pnl)
            await r.hincrbyfloat(self.TRACKING_STATS_KEY, f"rank{rank}:total_max_pnl", trade["max_pnl"])
            if trade["is_winner"]:
                await r.hincrby(self.TRACKING_STATS_KEY, f"rank{rank}:wins", 1)

            # Remove from memory
            del self._tracked_trades[trade_id]

            self.logger.info(
                f"[TRACKING] Settled: {trade['tile_key']} rank={rank} "
                f"final_pnl={final_pnl:.2f} max_pnl={trade['max_pnl']:.2f} "
                f"captured={trade['pnl_captured_pct']:.1f}%",
                emoji="🏁",
            )

            # Persist to journal for long-term analytics
            await self._persist_to_journal(trade)

    async def _update_tracking_totals(self) -> None:
        """
        Update cached totals for active trades.
        Sums from in-memory _tracked_trades (fast, no Redis read needed).
        SSE service reads these totals instead of fetching all trades.
        """
        if not self.tracking_enabled:
            return

        total_current_pnl = 0.0
        total_max_pnl = 0.0
        active_count = 0

        for trade in self._tracked_trades.values():
            if trade.get("status") == "active":
                total_current_pnl += trade.get("current_pnl", 0) or 0
                total_max_pnl += trade.get("max_pnl", 0) or 0
                active_count += 1

        r = await self._redis_conn()
        await r.hset(self.TRACKING_TOTALS_KEY, mapping={
            "total_current_pnl": str(round(total_current_pnl, 2)),
            "total_max_pnl": str(round(total_max_pnl, 2)),
            "active_count": str(active_count),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    async def _get_http_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session for API calls."""
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def _persist_to_journal(self, trade: Dict[str, Any]) -> None:
        """
        Persist a settled trade to the journal service for long-term analytics.
        This enables the feedback optimization loop.
        """
        try:
            session = await self._get_http_session()
            url = f"{self.journal_api_url}/api/internal/tracked-ideas"

            # Build payload for journal API
            payload = {
                "id": trade["trade_id"],
                "symbol": trade["symbol"],
                "entry_rank": trade["entry_rank"],
                "entry_time": trade["entry_time"],
                "entry_ts": int(trade["entry_ts"]),
                "entry_spot": trade["entry_spot"],
                "entry_vix": trade["entry_vix"],
                "entry_regime": trade["entry_regime"],
                # Time context
                "entry_hour": trade.get("entry_hour"),
                "entry_day_of_week": trade.get("entry_day_of_week"),
                # GEX context
                "entry_gex_flip": trade.get("entry_gex_flip"),
                "entry_gex_call_wall": trade.get("entry_gex_call_wall"),
                "entry_gex_put_wall": trade.get("entry_gex_put_wall"),
                # Trade params
                "strategy": trade["strategy"],
                "side": trade["side"],
                "strike": trade["strike"],
                "width": trade["width"],
                "dte": trade["dte"],
                "debit": trade["debit"],
                "max_profit_theoretical": trade["max_profit_theoretical"],
                "r2r_predicted": trade.get("r2r_predicted"),
                "campaign": trade.get("campaign"),
                "max_pnl": trade["max_pnl"],
                "max_pnl_time": trade.get("max_pnl_time"),
                "max_pnl_spot": trade.get("max_pnl_spot"),
                "settlement_time": trade["settlement_time"],
                "settlement_spot": trade["settlement_spot"],
                "final_pnl": trade["final_pnl"],
                "is_winner": trade["is_winner"],
                "pnl_captured_pct": trade.get("pnl_captured_pct"),
                "r2r_achieved": trade.get("r2r_achieved"),
                "edge_cases": trade.get("edge_cases", []),
                "params_version": self._active_params_version,
            }

            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    self.logger.debug(
                        f"[TRACKING] Persisted to journal: {trade['trade_id']}",
                        emoji="💾",
                    )
                else:
                    text = await resp.text()
                    self.logger.warn(
                        f"[TRACKING] Failed to persist to journal: {resp.status} - {text}",
                        emoji="⚠️",
                    )
        except Exception as e:
            # Don't fail settlement if journal is unavailable
            self.logger.warn(
                f"[TRACKING] Journal persistence error: {e}",
                emoji="⚠️",
            )

    async def _load_active_params_version(self) -> None:
        """Load the currently active params version from journal."""
        try:
            session = await self._get_http_session()
            url = f"{self.journal_api_url}/api/internal/selector-params/active"

            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success") and data.get("data"):
                        self._active_params_version = data["data"]["version"]
                        self.logger.info(
                            f"[TRACKING] Loaded active params version: {self._active_params_version}",
                            emoji="⚙️",
                        )
        except Exception as e:
            self.logger.warn(f"[TRACKING] Could not load active params: {e}", emoji="⚠️")

    async def _load_tracked_trades(self) -> None:
        """Load active tracked trades from Redis on startup."""
        if not self.tracking_enabled:
            return

        r = await self._redis_conn()
        active = await r.hgetall(self.TRACKING_ACTIVE_KEY)

        for trade_id, trade_json in active.items():
            try:
                trade = json.loads(trade_json)
                self._tracked_trades[trade_id] = trade
            except json.JSONDecodeError:
                continue

        if self._tracked_trades:
            self.logger.info(
                f"[TRACKING] Loaded {len(self._tracked_trades)} active trades from Redis",
                emoji="📊",
            )

    async def get_tracking_stats(self) -> Dict[str, Any]:
        """Get aggregate tracking statistics by rank."""
        r = await self._redis_conn()
        raw_stats = await r.hgetall(self.TRACKING_STATS_KEY)

        stats = {"by_rank": {}, "active_count": len(self._tracked_trades)}

        for rank in range(1, 11):
            count = int(raw_stats.get(f"rank{rank}:count", 0))
            if count == 0:
                continue

            wins = int(raw_stats.get(f"rank{rank}:wins", 0))
            total_pnl = float(raw_stats.get(f"rank{rank}:total_pnl", 0))
            total_max_pnl = float(raw_stats.get(f"rank{rank}:total_max_pnl", 0))

            stats["by_rank"][rank] = {
                "count": count,
                "wins": wins,
                "win_rate": wins / count if count > 0 else 0,
                "avg_pnl": total_pnl / count if count > 0 else 0,
                "avg_max_pnl": total_max_pnl / count if count > 0 else 0,
                "capture_rate": total_pnl / total_max_pnl if total_max_pnl > 0 else 0,
            }

        return stats

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
                    # Publish empty model so UI doesn't spin forever
                    ts_empty = time.time()
                    empty_model = {
                        "ts": ts_empty,
                        "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts_empty)),
                        "symbol": symbol,
                        "spot": None,
                        "error": "No spot data available",
                        "recommendations": {},
                        "total_scored": 0,
                    }
                    await r.set(
                        f"massive:selector:model:{symbol}:latest",
                        json.dumps(empty_model),
                        ex=self.model_ttl_sec,
                    )
                    self.logger.debug(f"[TRADE_SELECTOR] No spot for {symbol}, published empty model")
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

                # ML Feedback Loop: Cache market context once per build cycle
                if self.ml_enabled:
                    self._cache_ml_context(
                        spot=spot,
                        vix=vix,
                        vix3m=None,  # TODO: Load VIX3M
                        day_high=None,  # TODO: Load from spot model
                        day_low=None,
                        gex_context=bias_lfi,
                        bias_lfi=bias_lfi,
                    )

                all_scores: List[Dict[str, Any]] = []
                gamma_scalp_candidates: List[Dict[str, Any]] = []  # Separate list for gamma scalp
                filtered_count = 0  # Track tiles rejected by 5% filter
                ml_scored_count = 0  # Track ML-scored tiles

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
                        # HARD FILTER: 10% debit/width rule (minimum 1:9 R2R)
                        # E.g., 30-wide max $3.00, 20-wide max $2.00
                        # ==============================================
                        if not self._passes_debit_filter(width, debit):
                            filtered_count += 1
                            continue

                        # Get all debits at this strike for convexity calculation
                        all_debits_for_strike = debits_by_strike.get(strike, {})

                        # Determine campaign and edge cases for this trade
                        campaign = self._get_campaign(dte)
                        edge_cases = self._get_edge_cases(vix, current_hour, dte, regime)

                        # Calculate scores (Convexity is PRIMARY at 40%)
                        r2r_score = self._score_r2r(width, debit, dte)  # DTE-relative scoring
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

                        # ML Feedback Loop: Get ML score if enabled
                        ml_score = None
                        final_composite = composite
                        if self.ml_enabled:
                            idea_id = f"{symbol}:{tile_key}:{side}:{int(time.time())}"
                            ml_score, final_composite = await self._get_ml_score(
                                idea_id=idea_id,
                                strategy="butterfly",
                                side=side,
                                strike=strike,
                                width=width,
                                dte=dte,
                                debit=debit,
                                original_score=composite,
                            )
                            if ml_score is not None:
                                ml_scored_count += 1
                                # Log decision for feedback loop (sample ~1% to reduce volume)
                                if random.random() < 0.01:
                                    await self._log_ml_decision(
                                        idea_id=idea_id,
                                        original_score=composite,
                                        ml_score=ml_score,
                                        final_score=final_composite,
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

                        # Get R2R expectations for this DTE
                        r2r_expectations = self._get_r2r_expectations(dte)

                        all_scores.append({
                            "tile_key": scored_tile_key,
                            "composite": round(final_composite, 1),  # Use ML-blended score for sorting
                            "original_composite": round(composite, 1),  # Rule-based score
                            "ml_score": round(ml_score, 1) if ml_score is not None else None,
                            "confidence": round(confidence, 2),
                            "components": {
                                "r2r": round(r2r_score, 1),
                                "convexity": round(convexity_score, 1),
                                "width_fit": round(width_fit_score, 1),
                                "gamma_alignment": round(gamma_alignment_score, 1),
                            },
                            # Campaign info
                            "campaign": campaign,
                            "edge_cases": edge_cases,
                            # Tile details
                            "strategy": "butterfly",
                            "side": side,
                            "strike": strike,
                            "width": width,
                            "dte": dte,
                            "debit": round(debit, 2),
                            "debit_pct": round(debit_pct, 1),
                            # Computed
                            "max_profit": round(max_profit, 2),
                            "max_loss": round(max_loss, 2),
                            "r2r_ratio": round(r2r_ratio, 2),
                            "r2r_vs_typical": f"{r2r_ratio:.1f} vs {r2r_expectations['typical'][0]}-{r2r_expectations['typical'][1]}",
                            "distance_to_spot": round(distance_to_spot, 1),
                            "distance_to_gamma_magnet": round(distance_to_gamma_magnet, 1) if distance_to_gamma_magnet is not None else None,
                        })

                        # ==============================================
                        # GAMMA SCALP MODE: Score 0DTE near-ATM flies
                        # Late-day, high-gamma, structural squeeze play
                        # Works best in low VIX (wider time window)
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
                                    "campaign": "0dte_tactical",
                                    "edge_case": "gamma_scalp",
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
                        # Campaign info
                        "campaign": score["campaign"],
                        "edge_cases": score["edge_cases"],
                        "r2r_vs_typical": score["r2r_vs_typical"],
                        # Trade details
                        "strategy": score["strategy"],
                        "side": score["side"],
                        "strike": score["strike"],
                        "width": score["width"],
                        "dte": score["dte"],
                        "debit": score["debit"],
                        "debit_pct": score["debit_pct"],
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
                    "max_debit_pct": self.MAX_DEBIT_PCT * 100,  # 10%
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
                    # Scoring methodology
                    "scoring": {
                        "weights": {
                            "convexity": self.WEIGHT_CONVEXITY,  # PRIMARY: 40%
                            "r2r": self.WEIGHT_R2R,              # 25%
                            "width_fit": self.WEIGHT_WIDTH_FIT,  # 20%
                            "gamma_alignment": self.WEIGHT_GAMMA_ALIGNMENT,  # 15%
                        },
                        "hard_filter": f"debit <= {self.MAX_DEBIT_PCT * 100}% of width",
                        # ML Feedback Loop info
                        "ml_enabled": self.ml_enabled,
                        "ml_weight": self.ml_weight,
                        "ml_scored_count": ml_scored_count,
                    },
                    # Campaign definitions
                    "campaigns": self.CAMPAIGNS,
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
                    # Edge case availability
                    "edge_cases": {
                        "batman_available": vix >= self.BATMAN_VIX_THRESHOLD,
                        "timewarp_available": vix <= self.TIMEWARP_VIX_THRESHOLD,
                        "gamma_scalp_active": gamma_scalp_active,
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
                        "candidates": gamma_scalp_candidates[:5],
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

                # ----------------------------------------------------------
                # Trade Idea Tracking
                # ----------------------------------------------------------
                if self.tracking_enabled and recommendations:
                    # Track new entries into top 10
                    await self._track_new_entries(symbol, recommendations, spot, vix, regime, bias_lfi)

                    # Update P&L for all active tracked trades
                    await self._update_tracked_pnl(symbol, spot)

                    # Settle any expired trades
                    await self._settle_expired_trades(symbol, spot)

            # Update cached totals for SSE (after all symbols processed)
            if self.tracking_enabled:
                await self._update_tracking_totals()

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

        # Load any active tracked trades from Redis (resume tracking after restart)
        await self._load_tracked_trades()

        # Load active params version for tracking attribution
        await self._load_active_params_version()

        # Initialize ML engine if enabled
        if self.ml_enabled:
            await self._init_ml_engine()

        try:
            while not stop_event.is_set():
                t0 = time.monotonic()
                await self._build_once()
                dt = time.monotonic() - t0
                await asyncio.sleep(max(0.0, self.interval_sec - dt))
        finally:
            # Clean up HTTP session
            if self._http_session and not self._http_session.closed:
                await self._http_session.close()
            self.logger.info("[TRADE_SELECTOR STOP] halted", emoji="🛑")
