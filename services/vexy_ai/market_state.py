"""
MarketStateEngine — State of the Market (SoM) v2

Deterministic market-state synthesis for the Routine panel.
Four lenses: Big Picture Volatility, Localized Volatility,
Event Risk & Potential Energy, Convexity Temperature.

Philosophy: Calibrate posture — never recommend trades.
All reads from Redis (spot, GEX). No LLM, no external API.
Target: < 40ms response.
"""

from __future__ import annotations

import re
from datetime import datetime, date
from typing import Any, Dict, List, Optional

import pytz

from services.vexy_ai.intel.market_reader import MarketReader
from services.vexy_ai.routine_panel import (
    get_routine_context_phase,
    RoutineContextPhase,
    US_MARKET_HOLIDAYS_2025,
)

# ── VIX Regime Constants (frozen boundaries) ──────────────────────────

VIX_REGIMES = [
    {"max_vix": 15,   "key": "compression",   "label": "Compression",   "decay": "Narrow decay dominance",  "gamma": "Low"},
    {"max_vix": 20,   "key": "goldilocks_i",  "label": "Goldilocks I",  "decay": "Stable structured",       "gamma": "Normal"},
    {"max_vix": 28,   "key": "goldilocks_ii", "label": "Goldilocks II", "decay": "Balanced but alert",      "gamma": "Normal"},
    {"max_vix": 35,   "key": "elevated",      "label": "Elevated",      "decay": "Wider convexity",         "gamma": "High"},
    {"max_vix": 9999, "key": "chaos",          "label": "Chaos",         "decay": "Defensive posture",       "gamma": "Very High"},
]

# ── Language Sanitization ──────────────────────────────────────────────

FORBIDDEN_TOKENS = [
    "should", "enter", "exit", "avoid", "take profit",
    "stop loss", "expect", "likely",
]

_FORBIDDEN_RE = re.compile(
    r'\b(' + '|'.join(re.escape(t) for t in FORBIDDEN_TOKENS) + r')\b',
    re.IGNORECASE,
)

# ── Economic Calendar ──────────────────────────────────────────────────
# Hardcoded: ISO dates, times explicitly ET, impact enum.
# Covers FOMC, CPI, NFP, ISM, Fed speakers for 2025–2026.

ECONOMIC_CALENDAR: Dict[str, List[Dict[str, str]]] = {
    # ── 2025 ──
    "2025-01-10": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2025-01-14": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2025-01-15": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2025-01-29": [{"time_et": "14:00", "name": "FOMC Rate Decision", "impact": "Very High"}],
    "2025-02-07": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2025-02-12": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2025-02-13": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2025-03-03": [{"time_et": "10:00", "name": "ISM Manufacturing", "impact": "High"}],
    "2025-03-07": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2025-03-12": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2025-03-13": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2025-03-19": [{"time_et": "14:00", "name": "FOMC Rate Decision", "impact": "Very High"}],
    "2025-04-02": [{"time_et": "08:30", "name": "ADP Employment", "impact": "Medium"}],
    "2025-04-04": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2025-04-10": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2025-04-11": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2025-05-01": [{"time_et": "10:00", "name": "ISM Manufacturing", "impact": "High"}],
    "2025-05-02": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2025-05-07": [{"time_et": "14:00", "name": "FOMC Rate Decision", "impact": "Very High"}],
    "2025-05-13": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2025-05-14": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2025-06-02": [{"time_et": "10:00", "name": "ISM Manufacturing", "impact": "High"}],
    "2025-06-06": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2025-06-11": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2025-06-12": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2025-06-18": [{"time_et": "14:00", "name": "FOMC Rate Decision", "impact": "Very High"}],
    "2025-07-03": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2025-07-10": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2025-07-11": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2025-07-30": [{"time_et": "14:00", "name": "FOMC Rate Decision", "impact": "Very High"}],
    "2025-08-01": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2025-08-12": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2025-08-13": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2025-09-05": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2025-09-10": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2025-09-11": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2025-09-17": [{"time_et": "14:00", "name": "FOMC Rate Decision", "impact": "Very High"}],
    "2025-10-03": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2025-10-14": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2025-10-15": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2025-10-29": [{"time_et": "14:00", "name": "FOMC Rate Decision", "impact": "Very High"}],
    "2025-11-07": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2025-11-12": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2025-11-13": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2025-12-05": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2025-12-10": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2025-12-11": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2025-12-17": [{"time_et": "14:00", "name": "FOMC Rate Decision", "impact": "Very High"}],

    # ── 2026 ──
    "2026-01-09": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2026-01-14": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2026-01-15": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2026-01-28": [{"time_et": "14:00", "name": "FOMC Rate Decision", "impact": "Very High"}],
    "2026-02-06": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2026-02-11": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2026-02-12": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2026-03-06": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2026-03-11": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2026-03-12": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2026-03-18": [{"time_et": "14:00", "name": "FOMC Rate Decision", "impact": "Very High"}],
    "2026-04-03": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2026-04-14": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2026-04-15": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2026-05-01": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2026-05-06": [{"time_et": "14:00", "name": "FOMC Rate Decision", "impact": "Very High"}],
    "2026-05-12": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2026-05-13": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2026-06-05": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2026-06-10": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2026-06-11": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2026-06-17": [{"time_et": "14:00", "name": "FOMC Rate Decision", "impact": "Very High"}],
    "2026-07-02": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2026-07-14": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2026-07-15": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2026-07-29": [{"time_et": "14:00", "name": "FOMC Rate Decision", "impact": "Very High"}],
    "2026-08-07": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2026-08-12": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2026-08-13": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2026-09-04": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2026-09-16": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2026-09-17": [
        {"time_et": "08:30", "name": "PPI", "impact": "Medium"},
        {"time_et": "14:00", "name": "FOMC Rate Decision", "impact": "Very High"},
    ],
    "2026-10-02": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2026-10-13": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2026-10-14": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2026-10-28": [{"time_et": "14:00", "name": "FOMC Rate Decision", "impact": "Very High"}],
    "2026-11-06": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2026-11-10": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2026-11-12": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2026-12-04": [{"time_et": "08:30", "name": "NFP", "impact": "Very High"}],
    "2026-12-09": [{"time_et": "08:30", "name": "CPI", "impact": "Very High"}],
    "2026-12-10": [{"time_et": "08:30", "name": "PPI", "impact": "Medium"}],
    "2026-12-16": [{"time_et": "14:00", "name": "FOMC Rate Decision", "impact": "Very High"}],
}

# 2026 holidays
US_MARKET_HOLIDAYS_2026 = {
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # MLK Day
    "2026-02-16",  # Presidents Day
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-06-19",  # Juneteenth
    "2026-07-03",  # Independence Day (observed)
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving
    "2026-12-25",  # Christmas
}

ALL_HOLIDAYS = US_MARKET_HOLIDAYS_2025 | US_MARKET_HOLIDAYS_2026

# Weekend/off-market phases — SoM returns null lenses for these
_OFF_MARKET_PHASES = {
    RoutineContextPhase.FRIDAY_NIGHT,
    RoutineContextPhase.WEEKEND_MORNING,
    RoutineContextPhase.WEEKEND_AFTERNOON,
    RoutineContextPhase.WEEKEND_EVENING,
    RoutineContextPhase.HOLIDAY,
}


# ── Convexity Temperature Rules ───────────────────────────────────────
#
# | VIX Regime     | Event Energy                                       | Temperature |
# |----------------|----------------------------------------------------|-------------|
# | chaos          | any                                                | hot         |
# | elevated       | front_loaded / binary_event_day / high_energy_cluster | hot      |
# | elevated       | clean_morning / midday_loaded / speech_risk        | warm        |
# | goldilocks_ii  | binary_event_day / high_energy_cluster             | warm        |
# | goldilocks_ii  | clean_morning                                      | cool        |
# | goldilocks_i   | clean_morning                                      | cool        |
# | goldilocks_i   | any events                                         | warm        |
# | compression    | clean_morning                                      | cold        |
# | compression    | any events                                         | cool        |

_CONVEXITY_SUMMARIES = {
    "cold": "Low-energy environment. Decay dominates, convexity is cheap but slow.",
    "cool": "Calm conditions. Structured positions preferred, patience rewarded.",
    "warm": "Elevated energy. Environment supports structured convexity.",
    "hot": "High-energy regime. Wide strikes, defensive posture warranted.",
}


class MarketStateEngine:
    """Deterministic market-state synthesis for the Routine panel."""

    def __init__(self, market_reader: MarketReader, logger):
        self.market_reader = market_reader
        self.logger = logger

    # ── Lens 1: Big Picture Volatility ─────────────────────────────

    def get_vix_regime(self) -> Optional[Dict[str, Any]]:
        """Read VIX from market_reader and classify into 5-regime system."""
        try:
            spot = self.market_reader.get_spot("I:VIX")
            if not spot or spot.get("value") is None:
                self.logger.warning("VIX spot unavailable, using safe default", emoji="⚠️")
                return self._default_vix_regime()

            vix = float(spot["value"])
        except Exception as e:
            self.logger.warning(f"VIX read failed: {e}", emoji="⚠️")
            return self._default_vix_regime()

        for regime in VIX_REGIMES:
            if vix <= regime["max_vix"]:
                return {
                    "vix": round(vix, 1),
                    "regime_key": regime["key"],
                    "regime_label": regime["label"],
                    "decay_profile": regime["decay"],
                    "gamma_sensitivity": regime["gamma"],
                }

        # Fallback (shouldn't reach due to 9999 ceiling)
        return self._default_vix_regime()

    def _default_vix_regime(self) -> Dict[str, Any]:
        """Safe default when VIX is unavailable."""
        return {
            "vix": 0,
            "regime_key": "goldilocks_i",
            "regime_label": "Goldilocks I",
            "decay_profile": "Stable structured",
            "gamma_sensitivity": "Normal",
        }

    # ── Lens 2: Localized Volatility ──────────────────────────────

    def get_local_volatility(self) -> Optional[Dict[str, Any]]:
        """Derive dealer posture and expansion probability from GEX."""
        try:
            gex_data = self.market_reader.get_gex("I:SPX")
            spot_data = self.market_reader.get_spot("I:SPX")

            if not spot_data or spot_data.get("value") is None:
                self.logger.warning("SPX spot unavailable for local vol", emoji="⚠️")
                return self._default_local_vol()

            spot = float(spot_data["value"])
            bias = self.market_reader._compute_gex_bias(gex_data, spot)
            regime = bias.get("regime", "unknown")
        except Exception as e:
            self.logger.warning(f"GEX read failed: {e}", emoji="⚠️")
            return self._default_local_vol()

        if regime == "positive_gamma":
            dealer_posture = "long_gamma"
            expansion = "low"
            label = "Contained"
        elif regime == "negative_gamma":
            dealer_posture = "short_gamma"
            expansion = "high"
            label = "Fragile"
        else:
            dealer_posture = "neutral"
            expansion = "moderate"
            label = "Responsive"

        return {
            "dealer_posture": dealer_posture,
            "intraday_expansion_probability": expansion,
            "localized_vol_label": label,
        }

    def _default_local_vol(self) -> Dict[str, Any]:
        """Safe default when GEX is unavailable."""
        return {
            "dealer_posture": "neutral",
            "intraday_expansion_probability": "moderate",
            "localized_vol_label": "Responsive",
        }

    # ── Lens 3: Event Risk & Potential Energy ─────────────────────

    def get_event_energy(self) -> Dict[str, Any]:
        """Look up today's economic events and classify posture."""
        et = pytz.timezone("America/New_York")
        today_str = datetime.now(et).strftime("%Y-%m-%d")
        events = ECONOMIC_CALENDAR.get(today_str, [])

        if not events:
            return {
                "events": [],
                "event_posture": "clean_morning",
            }

        posture = self._classify_event_posture(events)

        return {
            "events": events,
            "event_posture": posture,
        }

    def _classify_event_posture(self, events: List[Dict[str, str]]) -> str:
        """Classify event posture from today's events."""
        impacts = [e.get("impact", "Low") for e in events]
        times = [e.get("time_et", "12:00") for e in events]

        has_very_high = "Very High" in impacts
        has_high = "High" in impacts
        high_count = impacts.count("Very High") + impacts.count("High")

        # Parse times to classify timing
        morning_events = [t for t in times if t < "10:00"]
        midday_events = [t for t in times if "10:00" <= t < "14:00"]
        afternoon_events = [t for t in times if t >= "14:00"]

        # High-energy cluster: 3+ high/very-high events
        if high_count >= 3:
            return "high_energy_cluster"

        # Binary event day: FOMC or very-high impact event in afternoon
        fomc_events = [e for e in events if "FOMC" in e.get("name", "")]
        if fomc_events:
            return "binary_event_day"

        # Front-loaded: very-high impact before 10:00
        if has_very_high and morning_events:
            return "front_loaded"

        # Midday-loaded: high+ impact between 10:00-14:00
        if (has_high or has_very_high) and midday_events:
            return "midday_loaded"

        # Speech risk: Fed speakers (heuristic — name contains "Fed" or "Speaker")
        speech_events = [e for e in events if "Fed" in e.get("name", "") or "Speaker" in e.get("name", "")]
        if speech_events:
            return "speech_risk"

        # Default — has events but nothing extreme
        return "front_loaded" if morning_events else "midday_loaded"

    # ── Lens 4: Convexity Temperature ─────────────────────────────

    def synthesize_convexity_temperature(
        self,
        vix_regime: Dict[str, Any],
        local_vol: Dict[str, Any],
        event_energy: Dict[str, Any],
    ) -> Dict[str, str]:
        """Deterministic synthesis from the other 3 lenses."""
        regime_key = vix_regime.get("regime_key", "goldilocks_i")
        posture = event_energy.get("event_posture", "clean_morning")

        temp = self._compute_temperature(regime_key, posture)

        return {
            "temperature": temp,
            "summary": _CONVEXITY_SUMMARIES[temp],
        }

    def _compute_temperature(self, regime_key: str, event_posture: str) -> str:
        """Apply the deterministic temperature rules."""
        hot_postures = {"front_loaded", "binary_event_day", "high_energy_cluster"}

        if regime_key == "chaos":
            return "hot"

        if regime_key == "elevated":
            if event_posture in hot_postures:
                return "hot"
            return "warm"

        if regime_key == "goldilocks_ii":
            if event_posture in {"binary_event_day", "high_energy_cluster"}:
                return "warm"
            if event_posture == "clean_morning":
                return "cool"
            return "warm"  # midday_loaded, speech_risk, front_loaded

        if regime_key == "goldilocks_i":
            if event_posture == "clean_morning":
                return "cool"
            return "warm"

        if regime_key == "compression":
            if event_posture == "clean_morning":
                return "cold"
            return "cool"

        # Fallback
        return "cool"

    # ── Full State Assembly ────────────────────────────────────────

    def get_full_state(self) -> Dict[str, Any]:
        """Assemble the complete SoM contract."""
        et = pytz.timezone("America/New_York")
        now = datetime.now(et)

        phase = get_routine_context_phase(now=now, holidays=ALL_HOLIDAYS)

        # Map RoutineContextPhase to contract context_phase values
        context_phase = self._map_context_phase(phase)

        envelope: Dict[str, Any] = {
            "schema_version": "som.v2",
            "generated_at": now.isoformat(),
            "context_phase": context_phase,
        }

        # Weekend/holiday: return null lenses
        if phase in _OFF_MARKET_PHASES:
            envelope["big_picture_volatility"] = None
            envelope["localized_volatility"] = None
            envelope["event_energy"] = None
            envelope["convexity_temperature"] = None
            return envelope

        # Active market — compute all lenses
        vix_regime = self.get_vix_regime()
        local_vol = self.get_local_volatility()
        event_energy = self.get_event_energy()
        convexity = self.synthesize_convexity_temperature(vix_regime, local_vol, event_energy)

        envelope["big_picture_volatility"] = vix_regime
        envelope["localized_volatility"] = local_vol
        envelope["event_energy"] = event_energy
        envelope["convexity_temperature"] = convexity

        # Language sanitization
        self._sanitize(envelope)

        return envelope

    def _map_context_phase(self, phase: RoutineContextPhase) -> str:
        """Map RoutineContextPhase enum to SoM contract values."""
        weekend_phases = {
            RoutineContextPhase.FRIDAY_NIGHT,
            RoutineContextPhase.WEEKEND_MORNING,
            RoutineContextPhase.WEEKEND_AFTERNOON,
            RoutineContextPhase.WEEKEND_EVENING,
        }
        if phase == RoutineContextPhase.HOLIDAY:
            return "holiday"
        if phase in weekend_phases:
            return "weekend"
        if phase == RoutineContextPhase.WEEKDAY_INTRADAY:
            return "weekday_live"
        return "weekday_premarket"

    def _sanitize(self, obj: Any) -> None:
        """Recursively scrub forbidden tokens from string values."""
        if isinstance(obj, dict):
            for key in list(obj.keys()):
                val = obj[key]
                if isinstance(val, str):
                    cleaned = _FORBIDDEN_RE.sub("***", val)
                    if cleaned != val:
                        self.logger.warning(f"Sanitized forbidden token in '{key}'", emoji="🚫")
                        obj[key] = cleaned
                else:
                    self._sanitize(val)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, str):
                    cleaned = _FORBIDDEN_RE.sub("***", item)
                    if cleaned != item:
                        obj[i] = cleaned
                else:
                    self._sanitize(item)


# ── Future-proofing TODOs (comment only, no implementation) ───────────
# TODO: VIX term structure slope (VIX vs VIX3M ratio)
# TODO: 0DTE IV percentile
# TODO: ATR percentile vs 20-day
# TODO: Volatility clustering detection
# TODO: Real economic API integration (replace hardcoded calendar)
