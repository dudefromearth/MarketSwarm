#!/usr/bin/env python3
# services/massive/intel/model_builders/bias_lfi.py
"""
Bias/LFI Model Builder

Calculates two key market structure metrics from GEX data:

1. Directional Strength (Bias): -100 to +100
   - Measures whether dealer hedging flow is supportive or hostile to price
   - Positive = supportive (net long gamma above spot absorbs rallies)
   - Negative = hostile (net short gamma amplifies selling)

2. LFI Score (Liquidity Flow Imbalance): 0 to 100
   - Measures how "sticky" vs "slippery" the current price level is
   - High LFI (>50) = absorbing (liquidity contains price, mean reversion)
   - Low LFI (<50) = accelerating (liquidity amplifies moves, trend)

Publishes to: massive:bias_lfi:model:latest
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from typing import Any, Dict, List, Tuple

from redis.asyncio import Redis


class BiasLfiModelBuilder:
    """
    Calculates directional strength and LFI from GEX distribution.
    """

    ANALYTICS_KEY = "massive:model:analytics"
    BUILDER_NAME = "bias_lfi"

    def __init__(self, config: Dict[str, Any], logger) -> None:
        self.config = config
        self.logger = logger

        self.symbols = [
            s.strip()
            for s in config.get("MASSIVE_CHAIN_SYMBOLS", "I:SPX,I:NDX").split(",")
            if s.strip()
        ]

        # Primary symbol for bias/lfi calculation (typically SPX)
        self.primary_symbol = config.get("MASSIVE_BIAS_LFI_SYMBOL", "I:SPX")

        self.interval_sec = int(config.get("MASSIVE_BIAS_LFI_INTERVAL_SEC", "5"))
        self.model_ttl_sec = int(config.get("MASSIVE_BIAS_LFI_TTL_SEC", "3600"))

        self.market_redis_url = config["buses"]["market-redis"]["url"]
        self._redis: Redis | None = None

        self.logger.info(
            f"[BIAS_LFI INIT] symbol={self.primary_symbol} interval={self.interval_sec}s",
            emoji="📊",
        )

    async def _redis_conn(self) -> Redis:
        if not self._redis:
            self._redis = Redis.from_url(self.market_redis_url, decode_responses=True)
        return self._redis

    async def _load_spot(self, symbol: str) -> float | None:
        """Load current spot price for symbol."""
        r = await self._redis_conn()
        raw = await r.get(f"massive:model:spot:{symbol}")
        if not raw:
            return None
        try:
            return float(json.loads(raw).get("value"))
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    async def _load_gex(self, symbol: str) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]]] | None:
        """
        Load GEX model for symbol.
        Returns (calls_gex, puts_gex) where each is {expiration: {strike: gex_value}}.
        """
        r = await self._redis_conn()

        calls_raw = await r.get(f"massive:gex:model:{symbol}:calls")
        puts_raw = await r.get(f"massive:gex:model:{symbol}:puts")

        if not calls_raw and not puts_raw:
            return None

        try:
            calls = json.loads(calls_raw) if calls_raw else {}
            puts = json.loads(puts_raw) if puts_raw else {}

            calls_exp = calls.get("expirations", {})
            puts_exp = puts.get("expirations", {})

            return calls_exp, puts_exp
        except json.JSONDecodeError:
            return None

    def _aggregate_gex_by_strike(
        self,
        calls_exp: Dict[str, Dict[str, float]],
        puts_exp: Dict[str, Dict[str, float]],
    ) -> Dict[float, Dict[str, float]]:
        """
        Aggregate GEX across all expirations by strike.
        Returns {strike: {"calls": total_call_gex, "puts": total_put_gex, "net": net_gex}}.

        Note: GEX model stores both calls and puts as positive values.
        For net GEX calculation:
        - Call GEX is positive (dealers long calls = positive gamma, resists rallies)
        - Put GEX is negative (dealers short puts = negative gamma, accelerates drops)
        """
        by_strike: Dict[float, Dict[str, float]] = {}

        # Aggregate calls (stored positive, keep positive)
        for exp, strikes in calls_exp.items():
            for strike_str, gex in strikes.items():
                try:
                    strike = float(strike_str)
                    if strike not in by_strike:
                        by_strike[strike] = {"calls": 0.0, "puts": 0.0, "net": 0.0}
                    by_strike[strike]["calls"] += gex
                except (ValueError, TypeError):
                    continue

        # Aggregate puts (stored positive, but represents negative gamma exposure)
        for exp, strikes in puts_exp.items():
            for strike_str, gex in strikes.items():
                try:
                    strike = float(strike_str)
                    if strike not in by_strike:
                        by_strike[strike] = {"calls": 0.0, "puts": 0.0, "net": 0.0}
                    # Store as negative for proper net calculation
                    by_strike[strike]["puts"] -= gex
                except (ValueError, TypeError):
                    continue

        # Calculate net GEX per strike (calls positive, puts negative)
        for strike in by_strike:
            by_strike[strike]["net"] = by_strike[strike]["calls"] + by_strike[strike]["puts"]

        return by_strike

    def _calculate_bias(
        self,
        gex_by_strike: Dict[float, Dict[str, float]],
        spot: float,
    ) -> float:
        """
        Calculate directional strength (bias) from GEX distribution.

        The bias measures where the "gamma gravity" pulls price:
        - Positive net GEX above spot = resistance (supportive, contains rallies)
        - Negative net GEX below spot = acceleration (hostile, amplifies drops)

        Returns value from -100 to +100.
        """
        if not gex_by_strike:
            return 0.0

        # Calculate net GEX above and below spot
        net_gex_above = 0.0  # Sum of net GEX at strikes above spot
        net_gex_below = 0.0  # Sum of net GEX at strikes below spot

        # Also calculate distance-weighted GEX for "center of gravity"
        weighted_gex_sum = 0.0
        total_abs_gex = 0.0

        for strike, gex_data in gex_by_strike.items():
            net_gex = gex_data["net"]
            abs_gex = abs(net_gex)

            if strike > spot:
                net_gex_above += net_gex
            elif strike < spot:
                net_gex_below += net_gex

            # Weight by distance from spot for center of gravity
            distance = strike - spot
            weighted_gex_sum += abs_gex * distance
            total_abs_gex += abs_gex

        if total_abs_gex == 0:
            return 0.0

        # Method 1: Compare net GEX above vs below
        # Positive above = supportive (resistance)
        # Negative below = hostile (acceleration)

        # Supportive: positive GEX above (resists rallies) OR positive GEX below (supports dips)
        # Hostile: negative GEX below (accelerates drops) OR negative GEX above (accelerates rallies)

        supportive = max(0, net_gex_above) + max(0, net_gex_below)
        hostile = abs(min(0, net_gex_below)) + abs(min(0, net_gex_above))

        total = supportive + hostile
        if total == 0:
            return 0.0

        # Method 2: Center of gravity - where is the gamma pulling price?
        gex_center = weighted_gex_sum / total_abs_gex  # Positive = above spot, negative = below

        # Normalize center by typical range (assume ~50 points is significant)
        center_bias = gex_center / 50.0  # Will be roughly -2 to +2 for typical distributions
        center_bias = max(-1, min(1, center_bias))  # Clamp to -1 to +1

        # Combine both methods:
        # - Net GEX imbalance (60% weight)
        # - Center of gravity (40% weight)

        imbalance_bias = (supportive - hostile) / total  # -1 to +1

        combined_bias = (imbalance_bias * 0.6 + center_bias * 0.4) * 100

        return max(-100, min(100, combined_bias))

    def _calculate_lfi(
        self,
        gex_by_strike: Dict[float, Dict[str, float]],
        spot: float,
    ) -> float:
        """
        Calculate LFI (Liquidity Flow Imbalance) score.

        LFI measures how "sticky" vs "slippery" the current price level is:
        - High LFI (>50) = absorbing (positive gamma near spot, dealers hedge aggressively)
        - Low LFI (<50) = accelerating (negative gamma near spot, dealers amplify moves)

        Key factors:
        1. Net GEX near spot (positive = absorbing, negative = accelerating)
        2. Concentration of GEX around spot vs dispersed
        3. The "gamma wall" effect - large GEX strikes nearby

        Returns value from 0 to 100.
        """
        if not gex_by_strike:
            return 50.0  # Neutral

        strikes = sorted(gex_by_strike.keys())
        if not strikes:
            return 50.0

        # Find the strikes nearest to spot
        total_abs_gex = sum(abs(g["net"]) for g in gex_by_strike.values())
        if total_abs_gex == 0:
            return 50.0

        # Calculate GEX in bands around spot
        # Near: within 0.5% of spot (very close)
        # Close: within 1% of spot
        # Medium: within 2% of spot

        near_pct = 0.005
        close_pct = 0.01
        medium_pct = 0.02

        gex_near = 0.0
        gex_close = 0.0
        gex_medium = 0.0
        abs_gex_near = 0.0
        abs_gex_close = 0.0
        abs_gex_medium = 0.0

        for strike, gex_data in gex_by_strike.items():
            net = gex_data["net"]
            pct_distance = abs(strike - spot) / spot

            if pct_distance <= near_pct:
                gex_near += net
                abs_gex_near += abs(net)
            if pct_distance <= close_pct:
                gex_close += net
                abs_gex_close += abs(net)
            if pct_distance <= medium_pct:
                gex_medium += net
                abs_gex_medium += abs(net)

        # Factor 1: Net GEX near spot (most important)
        # Positive = absorbing, Negative = accelerating
        # Scale: typical net GEX might be -50000 to +50000, map to 0-100

        if abs_gex_close > 0:
            # Ratio of net to absolute in close range
            # +1 = all positive (max absorbing), -1 = all negative (max accelerating)
            net_ratio = gex_close / abs_gex_close
        else:
            net_ratio = 0.0

        # Map net_ratio from [-1, +1] to [0, 100] with 50 as neutral
        net_factor = (net_ratio + 1) / 2 * 100  # 0 to 100

        # Factor 2: Concentration - what % of total GEX is within medium range?
        concentration = abs_gex_medium / total_abs_gex if total_abs_gex > 0 else 0
        # High concentration (>50%) = more absorbing, low (<20%) = more accelerating
        # Map concentration 0-1 to 30-70 contribution
        concentration_factor = 30 + concentration * 40

        # Factor 3: Magnitude of nearby GEX relative to total
        # Large GEX walls nearby = more absorbing
        nearby_magnitude = abs_gex_close / total_abs_gex if total_abs_gex > 0 else 0
        magnitude_factor = 40 + nearby_magnitude * 40  # 40-80 range

        # Combine factors with weights
        # Net ratio is most important (50%), then concentration (30%), then magnitude (20%)
        raw_lfi = (
            net_factor * 0.50 +
            concentration_factor * 0.30 +
            magnitude_factor * 0.20
        )

        return max(0, min(100, raw_lfi))

    def _find_flip_levels(
        self,
        gex_by_strike: Dict[float, Dict[str, float]],
        spot: float,
    ) -> Dict[str, Any]:
        """
        Find GEX flip levels (where net GEX changes sign).
        Returns the nearest flip level above and below spot.
        """
        strikes = sorted(gex_by_strike.keys())
        if not strikes:
            return {"flip_above": None, "flip_below": None, "nearest_flip": None}

        flip_above = None
        flip_below = None

        prev_strike = None
        prev_sign = None

        for strike in strikes:
            net = gex_by_strike[strike]["net"]
            if net == 0:
                continue

            current_sign = 1 if net > 0 else -1

            if prev_sign is not None and current_sign != prev_sign:
                # Found a flip between prev_strike and strike
                flip_point = (prev_strike + strike) / 2

                if flip_point < spot and (flip_below is None or flip_point > flip_below):
                    flip_below = flip_point
                elif flip_point > spot and flip_above is None:
                    flip_above = flip_point

            prev_strike = strike
            prev_sign = current_sign

        # Determine nearest flip
        nearest_flip = None
        if flip_above is not None and flip_below is not None:
            nearest_flip = flip_above if (flip_above - spot) < (spot - flip_below) else flip_below
        elif flip_above is not None:
            nearest_flip = flip_above
        elif flip_below is not None:
            nearest_flip = flip_below

        return {
            "flip_above": flip_above,
            "flip_below": flip_below,
            "nearest_flip": nearest_flip,
        }

    def _calculate_proximity_adjustment(
        self,
        gex_by_strike: Dict[float, Dict[str, float]],
        spot: float,
        flip_info: Dict[str, Any],
    ) -> Tuple[float, float]:
        """
        Calculate proximity adjustment factors for bias and LFI.

        When spot is close to a GEX flip level, the market is in a precarious
        position. This adjusts:
        - Bias: more negative (hostile) when near flip
        - LFI: lower (accelerating) when near flip

        Returns (bias_adjustment, lfi_adjustment) where:
        - bias_adjustment: -50 to 0 (subtracts from bias)
        - lfi_adjustment: -30 to 0 (subtracts from LFI)
        """
        nearest_flip = flip_info.get("nearest_flip")
        flip_below = flip_info.get("flip_below")

        if nearest_flip is None:
            return 0.0, 0.0

        # Calculate distance to nearest flip as percentage of spot
        distance_to_flip = abs(spot - nearest_flip)
        distance_pct = distance_to_flip / spot

        # Danger zone: within 0.5% of spot (~35 points for SPX at 7000)
        # Warning zone: within 1% of spot (~70 points)
        # Safe zone: beyond 1.5% of spot

        danger_threshold = 0.005  # 0.5%
        warning_threshold = 0.01  # 1%
        safe_threshold = 0.015   # 1.5%

        if distance_pct >= safe_threshold:
            # Safe - no adjustment
            proximity_factor = 0.0
        elif distance_pct <= danger_threshold:
            # Danger zone - maximum adjustment
            proximity_factor = 1.0
        else:
            # Warning zone - linear interpolation
            proximity_factor = 1.0 - (distance_pct - danger_threshold) / (safe_threshold - danger_threshold)

        # Additional penalty if spot is BELOW the flip (in negative gamma territory)
        # or if the flip is just below spot (about to fall into negative gamma)
        position_penalty = 0.0
        if flip_below is not None:
            if spot < flip_below:
                # Spot is below flip - in negative gamma territory
                position_penalty = 0.3
            elif (spot - flip_below) / spot < 0.003:
                # Flip is very close below spot (within 0.3%) - precarious
                position_penalty = 0.2

        # Calculate adjustments
        # Bias adjustment: push more negative when near flip
        # Max adjustment: -50 (turns +50 bias into 0, or 0 into -50)
        bias_adjustment = -50 * (proximity_factor + position_penalty)
        bias_adjustment = max(-50, bias_adjustment)

        # LFI adjustment: push lower (more accelerating) when near flip
        # Max adjustment: -30 (turns 60 LFI into 30)
        lfi_adjustment = -30 * (proximity_factor + position_penalty * 0.5)
        lfi_adjustment = max(-30, lfi_adjustment)

        return bias_adjustment, lfi_adjustment

    def _calculate_market_mode(
        self,
        bias: float,
        lfi: float,
        total_net_gex: float,
        spot: float,
    ) -> float:
        """
        Calculate Market Mode Score (0-100).

        The score represents the current market regime:
        - Compression (0-33): Negative gamma, hostile bias, low LFI
          - Dealers short gamma, moves amplified, squeeze potential
        - Transition (34-66): Mixed conditions, caution advised
          - Near gamma flip, moderate LFI
        - Expansion (67-100): Positive gamma, supportive bias, high LFI
          - Dealers long gamma, moves absorbed, range-bound

        Interpretation:
        - Low score = compressed/coiled, breakout imminent
        - High score = expanded/stable, mean reversion favored
        """
        # Factor 1: LFI directly (high LFI = high score = stable)
        # LFI 0-100 maps directly to contribution
        lfi_factor = lfi

        # Factor 2: Bias shifted to 0-100
        # Bias -100 to +100 maps to 0 to 100
        # Hostile (negative) = low score, Supportive (positive) = high score
        bias_factor = (bias + 100) / 2  # -100→0, 0→50, +100→100

        # Factor 3: Net GEX sign
        # Positive net GEX = stable/absorbed = high score
        # Negative net GEX = compressed/amplified = low score
        # Normalize by spot^2 * 0.0001 for typical GEX magnitude
        gex_normalized = total_net_gex / (spot * spot * 0.0001) if spot > 0 else 0
        # Typical range might be -50 to +50, map to 0-100
        gex_factor = 50 + gex_normalized  # Positive GEX → higher score
        gex_factor = max(0, min(100, gex_factor))

        # Combine factors with weights
        # LFI is most direct indicator (50%)
        # Bias indicates direction (30%)
        # Net GEX confirms regime (20%)
        raw_score = (
            lfi_factor * 0.50 +
            bias_factor * 0.30 +
            gex_factor * 0.20
        )

        return max(0, min(100, raw_score))

    def _calculate_additional_metrics(
        self,
        gex_by_strike: Dict[float, Dict[str, float]],
        spot: float,
    ) -> Dict[str, Any]:
        """Calculate additional context metrics."""
        if not gex_by_strike:
            return {}

        strikes = sorted(gex_by_strike.keys())
        if not strikes:
            return {}

        # Find key levels
        max_call_gex_strike = max(
            gex_by_strike.keys(),
            key=lambda s: gex_by_strike[s]["calls"],
            default=spot,
        )
        max_put_gex_strike = max(
            gex_by_strike.keys(),
            key=lambda s: abs(gex_by_strike[s]["puts"]),
            default=spot,
        )
        max_net_gex_strike = max(
            gex_by_strike.keys(),
            key=lambda s: gex_by_strike[s]["net"],
            default=spot,
        )

        # Total GEX
        total_call_gex = sum(g["calls"] for g in gex_by_strike.values())
        total_put_gex = sum(g["puts"] for g in gex_by_strike.values())
        total_net_gex = sum(g["net"] for g in gex_by_strike.values())

        # Find flip levels
        flip_info = self._find_flip_levels(gex_by_strike, spot)

        return {
            "max_call_gex_strike": max_call_gex_strike,
            "max_put_gex_strike": max_put_gex_strike,
            "max_net_gex_strike": max_net_gex_strike,
            "total_call_gex": total_call_gex,
            "total_put_gex": total_put_gex,
            "total_net_gex": total_net_gex,
            "gex_flip_level": flip_info.get("nearest_flip"),
            "flip_above": flip_info.get("flip_above"),
            "flip_below": flip_info.get("flip_below"),
            "strike_range": [min(strikes), max(strikes)] if strikes else None,
        }

    async def _build_once(self) -> None:
        """Main build cycle."""
        r = await self._redis_conn()
        t_start = time.monotonic()

        try:
            symbol = self.primary_symbol

            # Load spot price
            spot = await self._load_spot(symbol)
            if spot is None:
                self.logger.debug(f"[BIAS_LFI] No spot for {symbol}, skipping")
                return

            # Load GEX data
            gex_data = await self._load_gex(symbol)
            if gex_data is None:
                self.logger.debug(f"[BIAS_LFI] No GEX data for {symbol}, skipping")
                return

            calls_exp, puts_exp = gex_data

            # Aggregate GEX by strike
            gex_by_strike = self._aggregate_gex_by_strike(calls_exp, puts_exp)

            if not gex_by_strike:
                self.logger.debug(f"[BIAS_LFI] No GEX strikes for {symbol}, skipping")
                return

            # Calculate base metrics
            base_bias = self._calculate_bias(gex_by_strike, spot)
            base_lfi = self._calculate_lfi(gex_by_strike, spot)
            additional = self._calculate_additional_metrics(gex_by_strike, spot)

            # Calculate proximity adjustment based on distance to GEX flip level
            flip_info = self._find_flip_levels(gex_by_strike, spot)
            bias_adj, lfi_adj = self._calculate_proximity_adjustment(gex_by_strike, spot, flip_info)

            # Apply proximity adjustments
            directional_strength = max(-100, min(100, base_bias + bias_adj))
            lfi_score = max(0, min(100, base_lfi + lfi_adj))

            # Add adjustment info to additional metrics
            additional["proximity_bias_adj"] = round(bias_adj, 1)
            additional["proximity_lfi_adj"] = round(lfi_adj, 1)
            additional["distance_to_flip"] = round(abs(spot - flip_info["nearest_flip"]), 1) if flip_info.get("nearest_flip") else None

            # Calculate Market Mode Score (0-100)
            # Compression (0-33): Positive gamma, high LFI, supportive bias
            # Transition (34-66): Mixed conditions
            # Expansion (67-100): Negative gamma, low LFI, hostile bias
            market_mode_score = self._calculate_market_mode(
                directional_strength, lfi_score, additional.get("total_net_gex", 0), spot
            )

            # Build model
            ts = time.time()
            model = {
                "ts": ts,
                "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
                "symbol": symbol,
                "spot": spot,
                "directional_strength": round(directional_strength, 1),
                "lfi_score": round(lfi_score, 1),
                "market_mode_score": round(market_mode_score, 1),
                **additional,
            }

            # Publish bias_lfi model to Redis
            await r.set(
                "massive:bias_lfi:model:latest",
                json.dumps(model),
                ex=self.model_ttl_sec,
            )

            # Also publish per-symbol key for future multi-symbol support
            await r.set(
                f"massive:bias_lfi:model:{symbol}:latest",
                json.dumps(model),
                ex=self.model_ttl_sec,
            )

            # Publish market_mode model separately
            market_mode_model = {
                "ts": ts,
                "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
                "symbol": symbol,
                "score": round(market_mode_score, 1),
                "mode": "expansion" if market_mode_score >= 67 else "transition" if market_mode_score >= 34 else "compression",
            }
            await r.set(
                "massive:market_mode:model:latest",
                json.dumps(market_mode_model),
                ex=self.model_ttl_sec,
            )

            # Record analytics
            latency_ms = int((time.monotonic() - t_start) * 1000)
            await r.hincrby(self.ANALYTICS_KEY, f"{self.BUILDER_NAME}:runs", 1)
            await r.hset(self.ANALYTICS_KEY, f"{self.BUILDER_NAME}:latency_last_ms", latency_ms)

            self.logger.info(
                f"[BIAS_LFI] {symbol} bias={directional_strength:+.1f} lfi={lfi_score:.1f} mode={market_mode_score:.0f} ({latency_ms}ms)",
                emoji="📊",
            )

        except Exception as e:
            self.logger.error(f"[BIAS_LFI ERROR] {e}", emoji="💥")
            await r.hincrby(self.ANALYTICS_KEY, f"{self.BUILDER_NAME}:errors", 1)
            raise

    async def run(self, stop_event: asyncio.Event) -> None:
        """Main run loop."""
        self.logger.info("[BIAS_LFI START] running", emoji="🚀")
        try:
            while not stop_event.is_set():
                t0 = time.monotonic()
                await self._build_once()
                dt = time.monotonic() - t0
                await asyncio.sleep(max(0.0, self.interval_sec - dt))
        finally:
            self.logger.info("[BIAS_LFI STOP] halted", emoji="🛑")
