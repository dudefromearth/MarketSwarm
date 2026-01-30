"""
Volume Profile Effectiveness Calculator - MEL Model for Auction Structure.

Determines if auction theory is organizing price — or if balance/rotation logic
has broken down.

Expected Behaviors to Monitor:
- HVN acceptance rate (does price accept at high volume nodes?)
- LVN rejection rate (does price reject at low volume nodes?)
- Rotation completion (do rotations complete or abort?)
- Balance duration (how long do balance areas hold?)
- Initiative follow-through (do breakouts follow through?)

Failure/Stress Indicators:
- Poor rotation completion
- Balance breakdown frequency
- One-time-frame control
- Trend intrusions into balance

Session Structure:
- Open Auction: Normal/Extended/Failed
- Midday Balance: Stable/Fragile/Absent
- Late Session: Resolved/Unresolved/Chaotic
"""

from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime, timedelta
from enum import Enum
import logging

from .mel_calculator import MELCalculator
from .mel_models import MELConfig, Confidence


class AuctionState(str, Enum):
    """Current auction state."""
    BALANCE = "balance"
    INITIATIVE_UP = "initiative_up"
    INITIATIVE_DOWN = "initiative_down"
    ROTATION = "rotation"
    DISCOVERY = "discovery"


class VolumeProfileEffectivenessCalculator(MELCalculator):
    """
    Calculator for Volume Profile/Auction Structure effectiveness.

    Measures how well auction theory is organizing price behavior.
    """

    @property
    def model_name(self) -> str:
        return "volume_profile"

    def _get_required_data_fields(self) -> List[str]:
        return [
            "poc",
            "vah",
            "val",
            "hvns",
            "lvns",
            "price_history",
        ]

    def calculate_effectiveness(self, market_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate volume profile effectiveness score.

        Composite of:
        - HVN acceptance rate (25%)
        - LVN rejection rate (25%)
        - Rotation completion (20%)
        - Balance duration (15%)
        - Initiative follow-through (15%)
        """
        detail = {}

        # Extract data
        poc = market_data.get("poc")
        vah = market_data.get("vah")
        val = market_data.get("val")
        hvns = market_data.get("hvns", [])
        lvns = market_data.get("lvns", [])
        price_history = market_data.get("price_history", [])

        # If no data, return neutral score
        if not price_history or (poc is None and not hvns):
            return 65.0, {"note": "Insufficient data for volume profile effectiveness"}

        # Include POC in HVNs if not already
        all_hvns = list(hvns)
        if poc and poc not in all_hvns:
            all_hvns.append(poc)

        # 1. HVN Acceptance Rate (25%)
        detail["hvn_acceptance"] = self._calculate_hvn_acceptance_rate(
            price_history, all_hvns
        )

        # 2. LVN Rejection Rate (25%)
        detail["lvn_rejection"] = self._calculate_lvn_rejection_rate(
            price_history, lvns
        )

        # 3. Rotation Completion (20%)
        detail["rotation_completion"] = self._analyze_rotation_completion(
            price_history, vah, val
        )
        detail["rotation_score"] = self._score_rotation(detail["rotation_completion"])

        # 4. Balance Duration (15%)
        detail["balance_duration"] = self._analyze_balance_duration(
            price_history, vah, val
        )
        detail["balance_score"] = self._score_balance(detail["balance_duration"])

        # 5. Initiative Follow-Through (15%)
        detail["initiative_follow_through"] = self._analyze_initiative_follow_through(
            price_history, vah, val
        )
        detail["initiative_score"] = self._score_initiative(detail["initiative_follow_through"])

        # Stress indicators
        detail["stress_indicators"] = self._check_stress_indicators(
            market_data, detail, price_history, vah, val
        )

        # Session structure analysis
        detail["session_structure"] = self._analyze_session_structure(
            price_history, poc, vah, val
        )

        # Current auction state
        detail["auction_state"] = self._determine_auction_state(
            price_history, poc, vah, val
        )

        # Composite effectiveness score
        effectiveness = (
            detail["hvn_acceptance"] * 0.25 +
            detail["lvn_rejection"] * 0.25 +
            detail["rotation_score"] * 0.20 +
            detail["balance_score"] * 0.15 +
            detail["initiative_score"] * 0.15
        )

        return self.normalize_score(effectiveness), detail

    def _calculate_hvn_acceptance_rate(
        self,
        price_history: List[Dict],
        hvns: List[float],
    ) -> float:
        """
        Calculate percentage of times price accepts at high volume nodes.

        Acceptance = price approaches HVN and consolidates/dwells there.
        """
        if not price_history or not hvns:
            return 65.0

        tests = 0
        accepts = 0
        tolerance = 3.0  # Points tolerance for "at" HVN

        for i in range(1, len(price_history) - 2):
            curr_bar = price_history[i]
            curr_price = curr_bar.get("close") or curr_bar.get("price")

            if curr_price is None:
                continue

            for hvn in hvns:
                dist = abs(curr_price - hvn)

                if dist <= tolerance:
                    # Price is at HVN - this is a test
                    tests += 1

                    # Check if price dwells (stays near HVN for next few bars)
                    dwell_count = 0
                    for j in range(i + 1, min(i + 4, len(price_history))):
                        future_bar = price_history[j]
                        future_price = future_bar.get("close") or future_bar.get("price")
                        if future_price and abs(future_price - hvn) <= tolerance * 1.5:
                            dwell_count += 1

                    if dwell_count >= 2:
                        # Price accepted at HVN (dwelled)
                        accepts += 1
                    break  # Only count once per bar

        return self.calculate_rate(accepts, tests, 65.0)

    def _calculate_lvn_rejection_rate(
        self,
        price_history: List[Dict],
        lvns: List[float],
    ) -> float:
        """
        Calculate percentage of times price rejects at low volume nodes.

        Rejection = price approaches LVN and quickly moves away.
        """
        if not price_history or not lvns:
            return 65.0

        tests = 0
        rejects = 0
        tolerance = 2.0  # Points tolerance - LVNs should see fast moves

        for i in range(1, len(price_history) - 2):
            curr_bar = price_history[i]
            curr_price = curr_bar.get("close") or curr_bar.get("price")

            if curr_price is None:
                continue

            for lvn in lvns:
                dist = abs(curr_price - lvn)

                if dist <= tolerance:
                    # Price is at LVN - this is a test
                    tests += 1

                    # Check if price quickly moves away
                    if i + 2 < len(price_history):
                        future_bar = price_history[i + 2]
                        future_price = future_bar.get("close") or future_bar.get("price")

                        if future_price and abs(future_price - lvn) > tolerance * 2:
                            # Price moved away quickly - rejection
                            rejects += 1
                    break

        return self.calculate_rate(rejects, tests, 65.0)

    def _analyze_rotation_completion(
        self,
        price_history: List[Dict],
        vah: Optional[float],
        val: Optional[float],
    ) -> str:
        """
        Analyze whether rotations complete or abort.

        A rotation is a move from one value extreme to another.
        Complete = reaches the other extreme
        Abort = reverses before reaching

        Returns: 'Consistent', 'Inconsistent'
        """
        if not price_history or vah is None or val is None:
            return "Consistent"

        rotations_started = 0
        rotations_completed = 0

        mid_point = (vah + val) / 2
        threshold = (vah - val) * 0.3  # 30% of value area

        in_rotation = False
        rotation_target = None

        for bar in price_history:
            price = bar.get("close") or bar.get("price")
            if price is None:
                continue

            if not in_rotation:
                # Check if starting a rotation
                if abs(price - vah) < threshold:
                    # At VAH, rotation target is VAL
                    in_rotation = True
                    rotation_target = val
                    rotations_started += 1
                elif abs(price - val) < threshold:
                    # At VAL, rotation target is VAH
                    in_rotation = True
                    rotation_target = vah
                    rotations_started += 1
            else:
                # Check if rotation completed
                if rotation_target and abs(price - rotation_target) < threshold:
                    rotations_completed += 1
                    in_rotation = False
                    rotation_target = None
                # Check if rotation aborted (moved back to start)
                elif rotation_target == val and abs(price - vah) < threshold:
                    in_rotation = False
                    rotation_target = None
                elif rotation_target == vah and abs(price - val) < threshold:
                    in_rotation = False
                    rotation_target = None

        if rotations_started == 0:
            return "Consistent"

        completion_rate = rotations_completed / rotations_started

        if completion_rate >= 0.6:
            return "Consistent"
        else:
            return "Inconsistent"

    def _score_rotation(self, rotation: str) -> float:
        """Convert rotation completion to numeric score."""
        return self.score_categorical(rotation, {
            "Consistent": 85,
            "Inconsistent": 40,
        })

    def _analyze_balance_duration(
        self,
        price_history: List[Dict],
        vah: Optional[float],
        val: Optional[float],
    ) -> str:
        """
        Analyze how long balance areas hold.

        Balance = price staying within value area.

        Returns: 'Normal', 'Shortened', 'Extended'
        """
        if not price_history or vah is None or val is None:
            return "Normal"

        in_balance_count = 0
        total_bars = len(price_history)

        for bar in price_history:
            price = bar.get("close") or bar.get("price")
            if price and val <= price <= vah:
                in_balance_count += 1

        balance_pct = in_balance_count / total_bars * 100 if total_bars > 0 else 0

        # Expected: ~70% of time in balance for normal day
        if 60 <= balance_pct <= 80:
            return "Normal"
        elif balance_pct < 60:
            return "Shortened"  # Initiative day - less balance
        else:
            return "Extended"  # Very quiet day

    def _score_balance(self, balance: str) -> float:
        """Convert balance duration to numeric score."""
        return self.score_categorical(balance, {
            "Normal": 85,
            "Shortened": 60,  # Not bad, just trending
            "Extended": 70,   # Fine, just quiet
        })

    def _analyze_initiative_follow_through(
        self,
        price_history: List[Dict],
        vah: Optional[float],
        val: Optional[float],
    ) -> str:
        """
        Analyze whether breakouts from value area follow through.

        Returns: 'Strong', 'Mixed', 'Weak'
        """
        if not price_history or vah is None or val is None:
            return "Mixed"

        breakouts = 0
        follow_throughs = 0
        extension_threshold = (vah - val) * 0.5  # 50% of value area

        for i in range(len(price_history) - 5):
            bar = price_history[i]
            price = bar.get("close") or bar.get("price")

            if price is None:
                continue

            # Check for breakout above VAH
            if price > vah:
                breakouts += 1

                # Check for follow-through in next 5 bars
                max_extension = 0
                for j in range(i + 1, min(i + 6, len(price_history))):
                    future_bar = price_history[j]
                    future_price = future_bar.get("close") or future_bar.get("price")
                    if future_price:
                        extension = future_price - vah
                        max_extension = max(max_extension, extension)

                if max_extension >= extension_threshold:
                    follow_throughs += 1

            # Check for breakout below VAL
            elif price < val:
                breakouts += 1

                # Check for follow-through
                max_extension = 0
                for j in range(i + 1, min(i + 6, len(price_history))):
                    future_bar = price_history[j]
                    future_price = future_bar.get("close") or future_bar.get("price")
                    if future_price:
                        extension = val - future_price
                        max_extension = max(max_extension, extension)

                if max_extension >= extension_threshold:
                    follow_throughs += 1

        if breakouts == 0:
            return "Mixed"

        follow_through_rate = follow_throughs / breakouts

        if follow_through_rate >= 0.6:
            return "Strong"
        elif follow_through_rate >= 0.3:
            return "Mixed"
        else:
            return "Weak"

    def _score_initiative(self, initiative: str) -> float:
        """Convert initiative follow-through to numeric score."""
        return self.score_categorical(initiative, {
            "Strong": 90,
            "Mixed": 60,
            "Weak": 30,
        })

    def _check_stress_indicators(
        self,
        market_data: Dict[str, Any],
        detail: Dict[str, Any],
        price_history: List[Dict],
        vah: Optional[float],
        val: Optional[float],
    ) -> Dict[str, bool]:
        """Check for failure/stress indicators."""
        indicators = {
            "poor_rotation_completion": detail.get("rotation_completion") == "Inconsistent",
            "balance_breakdown_frequency": self._check_balance_breakdowns(price_history, vah, val),
            "one_time_frame_control": self._check_otf_control(price_history, vah, val),
            "trend_intrusions_into_balance": self._check_trend_intrusions(price_history, vah, val),
        }
        return indicators

    def _check_balance_breakdowns(
        self,
        price_history: List[Dict],
        vah: Optional[float],
        val: Optional[float],
    ) -> bool:
        """Check if balance areas are breaking down frequently."""
        if not price_history or vah is None or val is None:
            return False

        breakdowns = 0
        was_in_balance = True

        for bar in price_history:
            price = bar.get("close") or bar.get("price")
            if price is None:
                continue

            in_balance = val <= price <= vah

            if was_in_balance and not in_balance:
                breakdowns += 1

            was_in_balance = in_balance

        # More than 5 breakdowns per 100 bars is concerning
        breakdown_rate = breakdowns / len(price_history) * 100 if price_history else 0
        return breakdown_rate > 5

    def _check_otf_control(
        self,
        price_history: List[Dict],
        vah: Optional[float],
        val: Optional[float],
    ) -> bool:
        """
        Check for one-time-frame control.

        OTF = single timeframe dominating, no rotation.
        """
        if not price_history or vah is None or val is None:
            return False

        # Simple check: is price consistently on one side of value area?
        above_count = 0
        below_count = 0
        mid = (vah + val) / 2

        for bar in price_history[-20:]:  # Check recent bars
            price = bar.get("close") or bar.get("price")
            if price:
                if price > mid:
                    above_count += 1
                else:
                    below_count += 1

        total = above_count + below_count
        if total == 0:
            return False

        # If >80% of time on one side, it's OTF
        return max(above_count, below_count) / total > 0.8

    def _check_trend_intrusions(
        self,
        price_history: List[Dict],
        vah: Optional[float],
        val: Optional[float],
    ) -> bool:
        """Check if trend is constantly violating balance."""
        if not price_history or vah is None or val is None:
            return False

        # Count how often price breaks out and immediately returns
        false_breakouts = 0

        for i in range(len(price_history) - 3):
            bar = price_history[i]
            price = bar.get("close") or bar.get("price")
            if price is None:
                continue

            # Breakout above VAH
            if price > vah:
                # Check if it returns within 3 bars
                for j in range(i + 1, min(i + 4, len(price_history))):
                    future = price_history[j].get("close") or price_history[j].get("price")
                    if future and future < vah:
                        false_breakouts += 1
                        break

            # Breakout below VAL
            elif price < val:
                for j in range(i + 1, min(i + 4, len(price_history))):
                    future = price_history[j].get("close") or price_history[j].get("price")
                    if future and future > val:
                        false_breakouts += 1
                        break

        # More than 3 false breakouts is concerning
        return false_breakouts > 3

    def _analyze_session_structure(
        self,
        price_history: List[Dict],
        poc: Optional[float],
        vah: Optional[float],
        val: Optional[float],
    ) -> Dict[str, str]:
        """
        Analyze auction behavior by session phase.

        Returns behavior for Open Auction, Midday Balance, Late Session.
        """
        if not price_history:
            return {
                "open_auction": "Normal",
                "midday_balance": "Stable",
                "late_session": "Resolved",
            }

        total_bars = len(price_history)

        # Split into thirds for session phases
        open_bars = price_history[:total_bars // 3]
        midday_bars = price_history[total_bars // 3:2 * total_bars // 3]
        late_bars = price_history[2 * total_bars // 3:]

        return {
            "open_auction": self._classify_open_auction(open_bars, vah, val),
            "midday_balance": self._classify_midday_balance(midday_bars, vah, val),
            "late_session": self._classify_late_session(late_bars, poc, vah, val),
        }

    def _classify_open_auction(
        self,
        bars: List[Dict],
        vah: Optional[float],
        val: Optional[float],
    ) -> str:
        """Classify opening auction behavior."""
        if not bars:
            return "Normal"

        # Calculate opening range
        highs = [b.get("high") for b in bars if b.get("high")]
        lows = [b.get("low") for b in bars if b.get("low")]

        if not highs or not lows:
            return "Normal"

        open_range = max(highs) - min(lows)
        va_range = (vah - val) if vah and val else 20

        # Compare opening range to value area
        if open_range < va_range * 0.5:
            return "Normal"
        elif open_range < va_range * 1.0:
            return "Extended"
        else:
            return "Failed"  # Wild open, no structure

    def _classify_midday_balance(
        self,
        bars: List[Dict],
        vah: Optional[float],
        val: Optional[float],
    ) -> str:
        """Classify midday balance behavior."""
        if not bars or vah is None or val is None:
            return "Stable"

        in_balance = 0
        for bar in bars:
            price = bar.get("close") or bar.get("price")
            if price and val <= price <= vah:
                in_balance += 1

        balance_pct = in_balance / len(bars) * 100 if bars else 0

        if balance_pct >= 70:
            return "Stable"
        elif balance_pct >= 40:
            return "Fragile"
        else:
            return "Absent"

    def _classify_late_session(
        self,
        bars: List[Dict],
        poc: Optional[float],
        vah: Optional[float],
        val: Optional[float],
    ) -> str:
        """Classify late session resolution."""
        if not bars:
            return "Resolved"

        # Check if price settled near a reference point
        closes = [b.get("close") or b.get("price") for b in bars if b.get("close") or b.get("price")]

        if not closes:
            return "Unresolved"

        final_price = closes[-1]
        price_variance = max(closes) - min(closes) if len(closes) > 1 else 0

        # Low variance in late session = resolved
        va_range = (vah - val) if vah and val else 20

        if price_variance < va_range * 0.3:
            return "Resolved"
        elif price_variance < va_range * 0.6:
            return "Unresolved"
        else:
            return "Chaotic"

    def _determine_auction_state(
        self,
        price_history: List[Dict],
        poc: Optional[float],
        vah: Optional[float],
        val: Optional[float],
    ) -> str:
        """Determine current auction state."""
        if not price_history or vah is None or val is None:
            return AuctionState.BALANCE.value

        # Get recent price action
        recent = price_history[-5:] if len(price_history) >= 5 else price_history
        prices = [b.get("close") or b.get("price") for b in recent]
        prices = [p for p in prices if p]

        if not prices:
            return AuctionState.BALANCE.value

        current = prices[-1]
        trend = prices[-1] - prices[0] if len(prices) > 1 else 0

        # Determine state
        if current > vah:
            if trend > 0:
                return AuctionState.INITIATIVE_UP.value
            else:
                return AuctionState.ROTATION.value
        elif current < val:
            if trend < 0:
                return AuctionState.INITIATIVE_DOWN.value
            else:
                return AuctionState.ROTATION.value
        else:
            # In value area
            if abs(trend) < (vah - val) * 0.1:
                return AuctionState.BALANCE.value
            else:
                return AuctionState.ROTATION.value

    def _determine_confidence(
        self,
        detail: Dict[str, Any],
        market_data: Dict[str, Any],
    ) -> Confidence:
        """Determine confidence in the VP effectiveness score."""
        price_history = market_data.get("price_history", [])
        poc = market_data.get("poc")
        vah = market_data.get("vah")
        val = market_data.get("val")

        # Need sufficient history
        if len(price_history) < 20:
            return Confidence.LOW

        # Need value area defined
        if poc is None or vah is None or val is None:
            return Confidence.LOW

        if len(price_history) < 50:
            return Confidence.MEDIUM

        return Confidence.HIGH
