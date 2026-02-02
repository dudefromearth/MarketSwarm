# services/copilot/intel/reference_state_capture.py
"""
ReferenceStateCaptureService - Captures RiskGraph state snapshots.

Snapshots the current state of a strategy at:
- Prompt alert creation
- Sequential alert activation (relay with fresh baseline)

The reference state serves as the baseline against which deviations are measured.
"""

import json
from datetime import datetime, UTC
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class CapturedState:
    """Captured strategy state for reference comparison."""
    # Greeks
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None

    # P&L
    expiration_breakevens: Optional[list] = None
    theoretical_breakevens: Optional[list] = None
    max_profit: Optional[float] = None
    max_loss: Optional[float] = None
    pnl_at_spot: Optional[float] = None

    # Market
    spot_price: Optional[float] = None
    vix: Optional[float] = None
    market_regime: Optional[str] = None

    # Strategy
    dte: Optional[int] = None
    debit: Optional[float] = None
    strike: Optional[float] = None
    width: Optional[int] = None
    side: Optional[str] = None

    captured_at: str = ""

    def to_snapshot_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for ReferenceStateSnapshot creation."""
        return {
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "expiration_breakevens": json.dumps(self.expiration_breakevens) if self.expiration_breakevens else None,
            "theoretical_breakevens": json.dumps(self.theoretical_breakevens) if self.theoretical_breakevens else None,
            "max_profit": self.max_profit,
            "max_loss": self.max_loss,
            "pnl_at_spot": self.pnl_at_spot,
            "spot_price": self.spot_price,
            "vix": self.vix,
            "market_regime": self.market_regime,
            "dte": self.dte,
            "debit": self.debit,
            "strike": self.strike,
            "width": self.width,
            "side": self.side,
            "captured_at": self.captured_at,
        }


class ReferenceStateCaptureService:
    """
    Captures RiskGraph state snapshots for prompt alerts.

    Provides a baseline reference state that the PromptDrivenEvaluator
    compares against to detect deviations worth noticing.
    """

    def __init__(self, logger=None):
        self._logger = logger

    def _log(self, msg: str, level: str = "info"):
        if self._logger:
            fn = getattr(self._logger, level, self._logger.info)
            fn(msg)

    async def capture_for_alert(
        self,
        alert_id: str,
        strategy_id: str,
        strategy_data: Dict[str, Any],
        market_data: Optional[Dict[str, Any]] = None
    ) -> CapturedState:
        """
        Capture current RiskGraph state for an alert.

        Args:
            alert_id: The prompt alert ID this snapshot belongs to
            strategy_id: The strategy being monitored
            strategy_data: Current strategy state from RiskGraph
            market_data: Optional market context (spot, VIX, regime)

        Returns:
            CapturedState with all captured fields
        """
        market_data = market_data or {}

        captured = CapturedState(
            # Greeks
            delta=self._safe_float(strategy_data.get("delta")),
            gamma=self._safe_float(strategy_data.get("gamma")),
            theta=self._safe_float(strategy_data.get("theta")),

            # P&L
            expiration_breakevens=strategy_data.get("expiration_breakevens") or strategy_data.get("expirationBreakevens"),
            theoretical_breakevens=strategy_data.get("theoretical_breakevens") or strategy_data.get("theoreticalBreakevens"),
            max_profit=self._safe_float(strategy_data.get("max_profit") or strategy_data.get("maxProfit")),
            max_loss=self._safe_float(strategy_data.get("max_loss") or strategy_data.get("maxLoss")),
            pnl_at_spot=self._safe_float(strategy_data.get("pnl_at_spot") or strategy_data.get("pnlAtSpot")),

            # Market
            spot_price=self._safe_float(market_data.get("spot_price") or market_data.get("spot")),
            vix=self._safe_float(market_data.get("vix")),
            market_regime=market_data.get("market_regime") or market_data.get("gex_regime"),

            # Strategy
            dte=self._safe_int(strategy_data.get("dte")),
            debit=self._safe_float(strategy_data.get("debit") or strategy_data.get("current_debit")),
            strike=self._safe_float(strategy_data.get("strike")),
            width=self._safe_int(strategy_data.get("width")),
            side=strategy_data.get("side"),

            captured_at=datetime.now(UTC).isoformat(),
        )

        self._log(f"Captured reference state for alert {alert_id}: spot={captured.spot_price}, delta={captured.delta}, gamma={captured.gamma}")

        return captured

    async def capture_for_sequential_activation(
        self,
        alert_id: str,
        strategy_id: str,
        strategy_data: Dict[str, Any],
        market_data: Optional[Dict[str, Any]] = None
    ) -> CapturedState:
        """
        Capture fresh reference state when a sequential alert activates.

        In sequential orchestration (A -> B -> C), when alert A accomplishes
        its objective and alert B activates, B gets a fresh reference state
        captured at that moment rather than using A's old reference.

        Args:
            alert_id: The newly-activated alert ID
            strategy_id: The strategy being monitored
            strategy_data: Current strategy state
            market_data: Current market context

        Returns:
            CapturedState with fresh baseline
        """
        self._log(f"Capturing fresh reference for sequential activation: alert {alert_id}")
        return await self.capture_for_alert(alert_id, strategy_id, strategy_data, market_data)

    def compute_deviation(
        self,
        reference: CapturedState,
        current: CapturedState
    ) -> Dict[str, Any]:
        """
        Compute deviations between reference and current state.

        Args:
            reference: Baseline captured state
            current: Current state to compare

        Returns:
            Dictionary of deviations by metric
        """
        deviations = {}

        # Greeks deviations
        if reference.delta is not None and current.delta is not None:
            deviations["delta"] = {
                "reference": reference.delta,
                "current": current.delta,
                "change": current.delta - reference.delta,
                "pct_change": self._pct_change(reference.delta, current.delta)
            }

        if reference.gamma is not None and current.gamma is not None:
            deviations["gamma"] = {
                "reference": reference.gamma,
                "current": current.gamma,
                "change": current.gamma - reference.gamma,
                "pct_change": self._pct_change(reference.gamma, current.gamma)
            }

        if reference.theta is not None and current.theta is not None:
            deviations["theta"] = {
                "reference": reference.theta,
                "current": current.theta,
                "change": current.theta - reference.theta,
                "pct_change": self._pct_change(reference.theta, current.theta)
            }

        # P&L deviations
        if reference.max_profit is not None and current.pnl_at_spot is not None:
            profit_pct_ref = (reference.pnl_at_spot / reference.max_profit * 100) if reference.max_profit != 0 and reference.pnl_at_spot else 0
            profit_pct_cur = (current.pnl_at_spot / reference.max_profit * 100) if reference.max_profit != 0 and current.pnl_at_spot else 0

            deviations["profit_percentage"] = {
                "reference": profit_pct_ref,
                "current": profit_pct_cur,
                "change": profit_pct_cur - profit_pct_ref,
            }

        if reference.pnl_at_spot is not None and current.pnl_at_spot is not None:
            deviations["pnl"] = {
                "reference": reference.pnl_at_spot,
                "current": current.pnl_at_spot,
                "change": current.pnl_at_spot - reference.pnl_at_spot,
                "pct_change": self._pct_change(reference.pnl_at_spot, current.pnl_at_spot)
            }

        # Market deviations
        if reference.spot_price is not None and current.spot_price is not None:
            deviations["spot"] = {
                "reference": reference.spot_price,
                "current": current.spot_price,
                "change": current.spot_price - reference.spot_price,
                "pct_change": self._pct_change(reference.spot_price, current.spot_price)
            }

        if reference.vix is not None and current.vix is not None:
            deviations["vix"] = {
                "reference": reference.vix,
                "current": current.vix,
                "change": current.vix - reference.vix,
                "pct_change": self._pct_change(reference.vix, current.vix)
            }

        # Time deviation
        if reference.dte is not None and current.dte is not None:
            deviations["dte"] = {
                "reference": reference.dte,
                "current": current.dte,
                "days_elapsed": reference.dte - current.dte,
            }

        return deviations

    def should_skip_evaluation(
        self,
        reference: CapturedState,
        current: CapturedState,
        min_change_threshold: float = 0.01
    ) -> bool:
        """
        Determine if evaluation should be skipped due to minimal change.

        Cost optimization: Skip AI evaluation if nothing meaningful has changed.

        Args:
            reference: Baseline state
            current: Current state
            min_change_threshold: Minimum change to warrant evaluation (default 1%)

        Returns:
            True if evaluation should be skipped
        """
        deviations = self.compute_deviation(reference, current)

        # Check if any significant change occurred
        for metric, data in deviations.items():
            if "pct_change" in data:
                if abs(data["pct_change"]) >= min_change_threshold * 100:
                    return False  # Significant change - evaluate
            elif "change" in data:
                # For non-percentage metrics, check absolute change
                if metric == "dte" and data.get("days_elapsed", 0) >= 1:
                    return False  # DTE changed by at least 1 day
                elif metric == "profit_percentage" and abs(data.get("change", 0)) >= 5:
                    return False  # Profit changed by at least 5%

        return True  # No significant changes - skip

    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_int(self, value: Any) -> Optional[int]:
        """Safely convert value to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _pct_change(self, reference: float, current: float) -> float:
        """Calculate percentage change."""
        if reference == 0:
            return 0 if current == 0 else 100
        return ((current - reference) / abs(reference)) * 100
