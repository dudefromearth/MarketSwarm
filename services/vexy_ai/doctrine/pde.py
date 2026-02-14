"""
pde.py — Pattern Detection Engine.

Detects behavioral drift from Edge Lab trade data:
- Execution drift (declining exit discipline)
- Bias interference clusters (same-direction losses)
- Regime mismatch (trading against environment)
- Overtrading after loss (revenge sequences)
- Edge score decay (declining edge quality)
- Signature entropy collapse (style narrowing)

Constitutional constraint:
  PDE does NOT define truth. PDE does NOT override doctrine.
  PDE is observational only — generates alerts consumed by AOS.
  PDE never blocks or delays the LPD/DCL routing path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PatternCategory(Enum):
    EXECUTION_DRIFT = "execution_drift"
    BIAS_INTERFERENCE_CLUSTER = "bias_interference_cluster"
    REGIME_MISMATCH = "regime_mismatch"
    OVERTRADING_AFTER_LOSS = "overtrading_after_loss"
    EDGE_SCORE_DECAY = "edge_score_decay"
    SIGNATURE_ENTROPY_COLLAPSE = "signature_entropy_collapse"


@dataclass
class PatternAlert:
    """A detected behavioral pattern."""
    category: PatternCategory
    confidence: float
    sample_size: int
    summary: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


@dataclass
class PDEHealthMonitor:
    """Tracks PDE health for auto-disable logic."""
    MAX_CONSECUTIVE_FAILURES: int = 3
    MAX_SCAN_LATENCY_MS: int = 10_000

    consecutive_failures: int = 0
    auto_disabled: bool = False
    auto_disable_reason: Optional[str] = None
    last_scan_ts: Optional[float] = None
    last_scan_latency_ms: Optional[int] = None
    total_scans: int = 0
    total_failures: int = 0

    def record_success(self, latency_ms: int) -> None:
        self.consecutive_failures = 0
        self.last_scan_latency_ms = latency_ms
        self.last_scan_ts = time.time()
        self.total_scans += 1

        if latency_ms > self.MAX_SCAN_LATENCY_MS:
            self._auto_disable("latency_exceeded")
        elif self.auto_disabled:
            # Self-heal when healthy
            self._auto_enable()

    def record_failure(self, error: Exception) -> None:
        self.consecutive_failures += 1
        self.total_failures += 1
        self.last_scan_ts = time.time()

        if self.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            self._auto_disable("consecutive_failures")

    def _auto_disable(self, reason: str) -> None:
        self.auto_disabled = True
        self.auto_disable_reason = reason

    def _auto_enable(self) -> None:
        self.auto_disabled = False
        self.auto_disable_reason = None

    def get_status(self) -> Dict[str, Any]:
        return {
            "auto_disabled": self.auto_disabled,
            "auto_disable_reason": self.auto_disable_reason,
            "consecutive_failures": self.consecutive_failures,
            "total_scans": self.total_scans,
            "total_failures": self.total_failures,
            "last_scan_ts": self.last_scan_ts,
            "last_scan_latency_ms": self.last_scan_latency_ms,
        }


class PatternDetectionEngine:
    """
    Detects behavioral drift from Edge Lab trade data.

    Does NOT define truth. Does NOT override doctrine.
    Generates PatternAlerts consumed by AOS for overlay injection.
    """

    MIN_SAMPLE_SIZE = 10

    def __init__(self, logger: Any):
        self._logger = logger
        self.health = PDEHealthMonitor()
        self._recent_alerts: List[PatternAlert] = []
        self._max_alerts = 200

    def scan_user(self, user_id: int, trade_data: List[Dict]) -> List[PatternAlert]:
        """
        Run all pattern detectors against a user's trade data.

        Args:
            user_id: The user to scan
            trade_data: List of trade records from Edge Lab

        Returns:
            List of detected pattern alerts
        """
        t0 = time.time()
        alerts: List[PatternAlert] = []

        try:
            if len(trade_data) < self.MIN_SAMPLE_SIZE:
                self.health.record_success(int((time.time() - t0) * 1000))
                return alerts

            alerts.extend(self._detect_execution_drift(trade_data))
            alerts.extend(self._detect_bias_interference(trade_data))
            alerts.extend(self._detect_regime_mismatch(trade_data))
            alerts.extend(self._detect_overtrading_after_loss(trade_data))
            alerts.extend(self._detect_edge_score_decay(trade_data))
            alerts.extend(self._detect_entropy_collapse(trade_data))

            # Store and trim
            self._recent_alerts.extend(alerts)
            if len(self._recent_alerts) > self._max_alerts:
                self._recent_alerts = self._recent_alerts[-self._max_alerts:]

            latency_ms = int((time.time() - t0) * 1000)
            self.health.record_success(latency_ms)

            if alerts:
                self._logger.info(
                    f"PDE scan for user {user_id}: {len(alerts)} patterns detected ({latency_ms}ms)",
                    emoji="🔍",
                )

            return alerts

        except Exception as e:
            self.health.record_failure(e)
            self._logger.warning(f"PDE scan failed for user {user_id}: {e}", emoji="⚠️")
            return []

    def get_recent_alerts(self, limit: int = 50) -> List[Dict]:
        """Get recent alerts across all users."""
        alerts = self._recent_alerts[-limit:]
        return [
            {
                "category": a.category.value,
                "confidence": a.confidence,
                "sample_size": a.sample_size,
                "summary": a.summary,
                "ts": a.ts,
            }
            for a in reversed(alerts)
        ]

    # =================================================================
    # DETECTORS
    # =================================================================

    def _detect_execution_drift(self, trades: List[Dict]) -> List[PatternAlert]:
        """Detect declining exit discipline (holding losers too long)."""
        closed = [t for t in trades if t.get("status") == "closed" and t.get("pnl") is not None]
        if len(closed) < self.MIN_SAMPLE_SIZE:
            return []

        # Look at last N trades: ratio of trades held past stop
        recent = closed[-20:]
        losers = [t for t in recent if (t.get("pnl") or 0) < 0]
        if len(losers) < 3:
            return []

        # Check if recent loss magnitude is growing (avg loss increasing)
        half = len(losers) // 2
        if half < 2:
            return []

        early_avg = sum(abs(t.get("pnl", 0)) for t in losers[:half]) / half
        late_avg = sum(abs(t.get("pnl", 0)) for t in losers[half:]) / (len(losers) - half)

        if late_avg > early_avg * 1.3:  # 30% increase in avg loss size
            confidence = min(0.95, 0.5 + (late_avg / early_avg - 1.0))
            return [PatternAlert(
                category=PatternCategory.EXECUTION_DRIFT,
                confidence=round(confidence, 2),
                sample_size=len(recent),
                summary=f"Exit discipline has declined over the last {len(recent)} setups. "
                        f"Average loss size grew {int((late_avg/early_avg - 1) * 100)}%.",
                evidence={"early_avg_loss": round(early_avg, 2), "late_avg_loss": round(late_avg, 2)},
            )]
        return []

    def _detect_bias_interference(self, trades: List[Dict]) -> List[PatternAlert]:
        """Detect same-direction loss clusters (directional bias)."""
        closed = [t for t in trades if t.get("status") == "closed" and t.get("pnl") is not None]
        if len(closed) < self.MIN_SAMPLE_SIZE:
            return []

        recent = closed[-15:]
        losers = [t for t in recent if (t.get("pnl") or 0) < 0]
        if len(losers) < 4:
            return []

        # Check if losers cluster on one side
        sides = [t.get("side", "").lower() for t in losers]
        call_count = sides.count("call")
        put_count = sides.count("put")
        total = len(losers)

        dominant_side = "calls" if call_count > put_count else "puts"
        dominant_count = max(call_count, put_count)

        if dominant_count / total >= 0.75 and dominant_count >= 3:
            confidence = round(0.6 + (dominant_count / total - 0.75) * 2, 2)
            return [PatternAlert(
                category=PatternCategory.BIAS_INTERFERENCE_CLUSTER,
                confidence=min(0.95, confidence),
                sample_size=total,
                summary=f"{dominant_count} of {total} recent losses are on the {dominant_side} side. "
                        f"Possible directional bias interference.",
                evidence={"call_losses": call_count, "put_losses": put_count},
            )]
        return []

    def _detect_regime_mismatch(self, trades: List[Dict]) -> List[PatternAlert]:
        """Detect trading against the prevailing regime."""
        # Requires regime data on trades — stub if not present
        with_regime = [t for t in trades if t.get("regime") and t.get("status") == "closed"]
        if len(with_regime) < self.MIN_SAMPLE_SIZE:
            return []

        recent = with_regime[-15:]
        mismatches = 0
        for t in recent:
            regime = t.get("regime", "").lower()
            side = t.get("side", "").lower()
            pnl = t.get("pnl", 0) or 0

            # Simple heuristic: selling calls in bullish regime or selling puts in bearish
            if pnl < 0:
                if regime in ("bullish", "expansion") and side == "put":
                    mismatches += 1
                elif regime in ("bearish", "contraction") and side == "call":
                    mismatches += 1

        if mismatches >= 3:
            confidence = round(0.5 + (mismatches / len(recent)) * 0.5, 2)
            return [PatternAlert(
                category=PatternCategory.REGIME_MISMATCH,
                confidence=min(0.95, confidence),
                sample_size=len(recent),
                summary=f"{mismatches} of last {len(recent)} losing trades appear to contradict "
                        f"the prevailing market regime.",
                evidence={"mismatches": mismatches, "sample": len(recent)},
            )]
        return []

    def _detect_overtrading_after_loss(self, trades: List[Dict]) -> List[PatternAlert]:
        """Detect revenge trading sequences (rapid entries after losses)."""
        closed = [t for t in trades if t.get("status") == "closed" and t.get("entry_time")]
        if len(closed) < self.MIN_SAMPLE_SIZE:
            return []

        # Sort by entry time
        sorted_trades = sorted(closed, key=lambda t: t.get("entry_time", ""))
        revenge_sequences = 0

        for i in range(1, len(sorted_trades)):
            prev = sorted_trades[i - 1]
            curr = sorted_trades[i]

            prev_pnl = prev.get("pnl", 0) or 0
            if prev_pnl >= 0:
                continue

            # Check if next trade happened quickly (within same session — rough heuristic)
            prev_time = prev.get("exit_time") or prev.get("entry_time", "")
            curr_time = curr.get("entry_time", "")

            if prev_time and curr_time and prev_time[:10] == curr_time[:10]:
                # Same day, loss followed by another trade
                curr_pnl = curr.get("pnl", 0) or 0
                if curr_pnl < 0:
                    revenge_sequences += 1

        if revenge_sequences >= 3:
            confidence = round(0.5 + min(revenge_sequences * 0.1, 0.4), 2)
            return [PatternAlert(
                category=PatternCategory.OVERTRADING_AFTER_LOSS,
                confidence=confidence,
                sample_size=len(sorted_trades),
                summary=f"Detected {revenge_sequences} same-day loss-then-loss sequences "
                        f"suggesting revenge trading pattern.",
                evidence={"revenge_sequences": revenge_sequences},
            )]
        return []

    def _detect_edge_score_decay(self, trades: List[Dict]) -> List[PatternAlert]:
        """Detect declining edge quality over time."""
        with_edge = [t for t in trades if t.get("edge_score") is not None and t.get("status") == "closed"]
        if len(with_edge) < self.MIN_SAMPLE_SIZE:
            return []

        recent = with_edge[-20:]
        half = len(recent) // 2
        if half < 3:
            return []

        early_avg = sum(t.get("edge_score", 0) for t in recent[:half]) / half
        late_avg = sum(t.get("edge_score", 0) for t in recent[half:]) / (len(recent) - half)

        if early_avg > 0 and late_avg < early_avg * 0.7:  # 30%+ decline
            confidence = round(0.5 + (1 - late_avg / early_avg) * 0.5, 2)
            return [PatternAlert(
                category=PatternCategory.EDGE_SCORE_DECAY,
                confidence=min(0.95, confidence),
                sample_size=len(recent),
                summary=f"Edge quality has declined {int((1 - late_avg/early_avg) * 100)}% "
                        f"over the last {len(recent)} setups.",
                evidence={"early_avg_edge": round(early_avg, 2), "late_avg_edge": round(late_avg, 2)},
            )]
        return []

    def _detect_entropy_collapse(self, trades: List[Dict]) -> List[PatternAlert]:
        """Detect narrowing of trading style (strategy diversity loss)."""
        closed = [t for t in trades if t.get("status") == "closed" and t.get("strategy")]
        if len(closed) < self.MIN_SAMPLE_SIZE:
            return []

        recent = closed[-20:]
        strategies = [t.get("strategy", "unknown") for t in recent]
        unique = set(strategies)

        # If using only 1 strategy across 10+ trades
        if len(unique) == 1 and len(recent) >= 10:
            return [PatternAlert(
                category=PatternCategory.SIGNATURE_ENTROPY_COLLAPSE,
                confidence=0.70,
                sample_size=len(recent),
                summary=f"All {len(recent)} recent trades use a single strategy: {strategies[0]}. "
                        f"Consider whether style narrowing is intentional.",
                evidence={"strategies": list(unique), "count": len(recent)},
            )]

        # If dominant strategy > 80% of trades
        from collections import Counter
        counts = Counter(strategies)
        most_common, mc_count = counts.most_common(1)[0]
        if mc_count / len(recent) > 0.80 and mc_count >= 8:
            confidence = round(0.5 + (mc_count / len(recent) - 0.8) * 2.5, 2)
            return [PatternAlert(
                category=PatternCategory.SIGNATURE_ENTROPY_COLLAPSE,
                confidence=min(0.90, confidence),
                sample_size=len(recent),
                summary=f"{mc_count} of {len(recent)} recent trades use '{most_common}'. "
                        f"Strategy diversity has narrowed.",
                evidence={"dominant": most_common, "ratio": round(mc_count / len(recent), 2)},
            )]
        return []
