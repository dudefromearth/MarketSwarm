# services/copilot/intel/algo_alert_evaluator.py
"""
Algo-Alert Evaluator — Position State Machine for Risk Graph.

Filter Engine + Structure Proposer + Management Assessor.

Core architecture (Vexy's framework):
  DATA → FILTERS (permission engine) → STATE ACTION → TRADER CONFIRMS

Guardrails:
- Filters != triggers — FilterEngine is a permission gate only
- Fail-closed — missing/conflicting data → filter fails → no proposal
- No prediction — system answers "is structure acceptable?" not "will price go up?"
- Silence > bad automation — no action on ambiguity
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .alert_engine import AlertEvaluation, BaseEvaluator


# ==================== Data Classes ====================

@dataclass
class FilterCondition:
    """A single structured filter gate."""
    id: str
    data_source: str  # gex, market_mode, bias_lfi, vix_regime, volume_profile, price, dte, trade_selector, position
    field: str
    operator: str     # gt, lt, eq, gte, lte, between, in, not_in
    value: Any        # number, string, list
    required: bool = True


@dataclass
class FilterEvaluationResult:
    """Per-filter evaluation result."""
    filter_id: str
    data_source: str
    field: str
    passed: bool
    current_value: Any
    target_value: Any
    data_available: bool


@dataclass
class ConvexityGateResult:
    """Result from the convexity feasibility check."""
    feasible: bool
    reason: str


@dataclass
class SuggestedPosition:
    """A proposed position structure."""
    strategy_type: str
    strike: float
    width: int
    side: str  # call or put
    dte: int
    expiration: str
    estimated_debit: float
    symbol: str = "SPX"


@dataclass
class ManagementRecommendation:
    """A management action recommendation."""
    action: str  # exit, tighten, hold, adjust
    reasoning: str
    risk_score: float  # 0-100


@dataclass
class AlgoAlertState:
    """Internal tracking state for an algo alert across evaluation cycles."""
    alert_id: str
    recent_pass_results: List[bool] = field(default_factory=list)  # Last N eval results
    frozen_cycles: int = 0
    stable_cycles: int = 0
    pending_proposal_id: Optional[str] = None
    last_proposal_at: Optional[float] = None

    MAX_HISTORY = 6  # Track last 6 evaluations for oscillation detection
    OSCILLATION_THRESHOLD = 3  # 3 state changes in 6 cycles = oscillating
    STABLE_RESUME_THRESHOLD = 4  # 4 consecutive stable results to unfreeze


# ==================== Filter Engine ====================

class FilterEngine:
    """
    Evaluates structured filter conditions against live market data.

    Fail-closed: if required=True and data is missing, filter fails.
    This is a permission gate, not a trigger.
    """

    # Map data_source to market_data keys
    SOURCE_KEY_MAP = {
        "gex": "gex",
        "market_mode": "market_mode",
        "bias_lfi": "bias_lfi",
        "vix_regime": "vix_regime",
        "volume_profile": "volume_profile",
        "price": "price",
        "dte": "dte",
        "trade_selector": "trade_selector",
        "position": "position",
    }

    def evaluate(
        self,
        filters: List[FilterCondition],
        market_data: dict,
    ) -> Tuple[bool, List[FilterEvaluationResult]]:
        """
        Evaluate all filters against market data.

        Returns (all_passed, results).
        All filters must pass for all_passed=True.
        """
        results = []
        all_passed = True

        for f in filters:
            result = self._evaluate_single(f, market_data)
            results.append(result)
            if not result.passed:
                all_passed = False

        return all_passed, results

    def _evaluate_single(
        self, f: FilterCondition, market_data: dict
    ) -> FilterEvaluationResult:
        """Evaluate a single filter condition."""
        source_key = self.SOURCE_KEY_MAP.get(f.data_source)
        if not source_key:
            return FilterEvaluationResult(
                filter_id=f.id,
                data_source=f.data_source,
                field=f.field,
                passed=False,
                current_value=None,
                target_value=f.value,
                data_available=False,
            )

        # Extract the data source dict from market_data
        source_data = market_data.get(source_key)

        # Special handling for flat fields (price → spot_price, dte → dte value)
        if f.data_source == "price" and f.field == "spot":
            current_value = market_data.get("spot_price") or market_data.get("spot")
            data_available = current_value is not None
        elif f.data_source == "dte" and f.field == "dte":
            current_value = market_data.get("dte")
            data_available = current_value is not None
        elif source_data is None:
            # Fail-closed on missing data source
            return FilterEvaluationResult(
                filter_id=f.id,
                data_source=f.data_source,
                field=f.field,
                passed=not f.required,  # Only pass if not required
                current_value=None,
                target_value=f.value,
                data_available=False,
            )
        elif isinstance(source_data, dict):
            current_value = source_data.get(f.field)
            data_available = current_value is not None
        else:
            current_value = source_data
            data_available = current_value is not None

        # Fail-closed: missing data + required = fail
        if not data_available:
            return FilterEvaluationResult(
                filter_id=f.id,
                data_source=f.data_source,
                field=f.field,
                passed=not f.required,
                current_value=None,
                target_value=f.value,
                data_available=False,
            )

        # Apply operator
        passed = self._apply_operator(f.operator, current_value, f.value)

        return FilterEvaluationResult(
            filter_id=f.id,
            data_source=f.data_source,
            field=f.field,
            passed=passed,
            current_value=current_value,
            target_value=f.value,
            data_available=True,
        )

    def _apply_operator(self, operator: str, current: Any, target: Any) -> bool:
        """Apply a comparison operator."""
        try:
            if operator == "gt":
                return float(current) > float(target)
            elif operator == "lt":
                return float(current) < float(target)
            elif operator == "eq":
                if isinstance(target, str):
                    return str(current).lower() == target.lower()
                return float(current) == float(target)
            elif operator == "gte":
                return float(current) >= float(target)
            elif operator == "lte":
                return float(current) <= float(target)
            elif operator == "between":
                if isinstance(target, (list, tuple)) and len(target) == 2:
                    return float(target[0]) <= float(current) <= float(target[1])
                return False
            elif operator == "in":
                if isinstance(target, (list, tuple)):
                    return str(current).lower() in [str(t).lower() for t in target]
                return str(current).lower() == str(target).lower()
            elif operator == "not_in":
                if isinstance(target, (list, tuple)):
                    return str(current).lower() not in [str(t).lower() for t in target]
                return str(current).lower() != str(target).lower()
        except (ValueError, TypeError):
            return False
        return False


# ==================== Convexity Gate ====================

class ConvexityGate:
    """
    Mode A pre-check: validates that a convex shape can exist
    on the current surface before StructureProposer runs.

    If no acceptable convex shape exists → halt, do NOT propose.
    """

    def check(self, market_data: dict, constraints: Optional[dict] = None) -> ConvexityGateResult:
        """
        Check whether the current options surface supports
        an asymmetric payoff at any valid strike/width.

        Uses GEX data + spot price to determine if structure is feasible.
        """
        spot = market_data.get("spot_price") or market_data.get("spot")
        if spot is None:
            return ConvexityGateResult(
                feasible=False,
                reason="No spot price available — cannot assess surface",
            )

        gamma_levels = market_data.get("gamma_levels", [])
        if not gamma_levels:
            return ConvexityGateResult(
                feasible=False,
                reason="No gamma level data available — cannot assess convexity",
            )

        # Check if there are strikes with positive net gamma near spot
        # (positive gamma = convexity opportunity)
        spot_f = float(spot)
        nearby_range = spot_f * 0.03  # 3% range around spot

        positive_gamma_strikes = [
            gl for gl in gamma_levels
            if abs(gl["strike"] - spot_f) <= nearby_range and gl["net_gamma"] > 0
        ]

        if not positive_gamma_strikes:
            return ConvexityGateResult(
                feasible=False,
                reason="No positive gamma concentration near spot — no convex shape available",
            )

        # Check trade selector for viable candidates if available
        trade_selector = market_data.get("trade_selector")
        if trade_selector and isinstance(trade_selector, dict):
            top_score = trade_selector.get("top_score", 0)
            if top_score > 0 and trade_selector.get("has_recommendation"):
                return ConvexityGateResult(
                    feasible=True,
                    reason=f"Convex shape available — trade selector score {top_score}",
                )

        # Basic feasibility: gamma structure supports a convex shape
        return ConvexityGateResult(
            feasible=True,
            reason=f"Convex shape feasible — {len(positive_gamma_strikes)} positive gamma strikes near spot",
        )


# ==================== Structure Proposer ====================

class StructureProposer:
    """
    Mode A: generates entry suggestions.

    Only runs if ConvexityGate passes. Uses trade_selector data if available.
    NO FALLBACK: if no valid candidate → no proposal.
    """

    def propose(
        self,
        market_data: dict,
        constraints: Optional[dict] = None,
    ) -> Optional[SuggestedPosition]:
        """
        Generate an entry suggestion based on trade selector and constraints.

        Returns None if no valid candidate exists.
        """
        spot = market_data.get("spot_price") or market_data.get("spot")
        if spot is None:
            return None

        spot_f = float(spot)

        # Use trade selector recommendation if available
        trade_selector = market_data.get("trade_selector")
        if trade_selector and isinstance(trade_selector, dict):
            rec = trade_selector.get("recommendation")
            if rec and isinstance(rec, dict):
                return SuggestedPosition(
                    strategy_type=rec.get("strategy_type", "butterfly"),
                    strike=float(rec.get("strike", spot_f)),
                    width=int(rec.get("width", 10)),
                    side=rec.get("side", "put"),
                    dte=int(rec.get("dte", 0)),
                    expiration=rec.get("expiration", ""),
                    estimated_debit=float(rec.get("estimated_debit", 0)),
                    symbol=rec.get("symbol", "SPX"),
                )

        # Use gamma structure to suggest OTM butterfly at zero gamma
        zero_gamma = market_data.get("zero_gamma")
        gamma_magnet = market_data.get("gamma_magnet")
        if zero_gamma is not None:
            # Determine side based on spot vs zero gamma
            side = "put" if zero_gamma < spot_f else "call"
            strike = int(round(zero_gamma / 5) * 5)  # Round to nearest 5-point strike

            # Apply constraints
            max_risk = 500  # Default
            preferred_width = 10
            preferred_dte = 0
            if constraints:
                max_risk = constraints.get("maxRisk", max_risk)
                preferred_width = constraints.get("preferredWidth", preferred_width)
                dte_range = constraints.get("preferredDteRange")
                if dte_range and len(dte_range) == 2:
                    preferred_dte = dte_range[0]

            dte_data = market_data.get("dte")
            expiration = market_data.get("expiration", "")

            return SuggestedPosition(
                strategy_type="butterfly",
                strike=strike,
                width=preferred_width,
                side=side,
                dte=dte_data if dte_data is not None else preferred_dte,
                expiration=expiration,
                estimated_debit=min(max_risk * 0.5, 300),  # Conservative estimate
                symbol="SPX",
            )

        # No valid candidate — silence is correct
        return None


# ==================== Management Assessor ====================

class ManagementAssessor:
    """
    Mode B: evaluates position health against current market structure.

    Returns recommendation: exit/tighten/hold with reasoning.
    """

    def assess(
        self,
        filter_results: List[FilterEvaluationResult],
        market_data: dict,
        position_data: Optional[dict] = None,
    ) -> ManagementRecommendation:
        """
        Assess position health based on filter results and market data.
        """
        # Count failed structural filters
        total_filters = len(filter_results)
        failed_filters = [r for r in filter_results if not r.passed and r.data_available]
        unavailable_filters = [r for r in filter_results if not r.data_available]

        if total_filters == 0:
            return ManagementRecommendation(
                action="hold",
                reasoning="No filters configured — holding by default",
                risk_score=50.0,
            )

        failed_count = len(failed_filters)
        unavailable_count = len(unavailable_filters)
        pass_rate = (total_filters - failed_count - unavailable_count) / total_filters

        # Build reasoning from failed filters
        failure_reasons = []
        for r in failed_filters:
            failure_reasons.append(
                f"{r.data_source}.{r.field}: current={r.current_value}, expected {r.target_value}"
            )

        risk_score = (1 - pass_rate) * 100

        # Decision thresholds
        if failed_count == 0 and unavailable_count == 0:
            return ManagementRecommendation(
                action="hold",
                reasoning="All structural filters passing — position structure intact",
                risk_score=risk_score,
            )

        if unavailable_count > 0 and failed_count == 0:
            return ManagementRecommendation(
                action="hold",
                reasoning=f"{unavailable_count} data source(s) unavailable — holding with caution",
                risk_score=max(risk_score, 30.0),
            )

        if pass_rate >= 0.7:
            return ManagementRecommendation(
                action="hold",
                reasoning=f"Structure mostly intact ({failed_count} filter(s) failing): {'; '.join(failure_reasons[:2])}",
                risk_score=risk_score,
            )

        if pass_rate >= 0.4:
            return ManagementRecommendation(
                action="tighten",
                reasoning=f"Structure degrading ({failed_count}/{total_filters} filters failing): {'; '.join(failure_reasons[:3])}",
                risk_score=risk_score,
            )

        return ManagementRecommendation(
            action="exit",
            reasoning=f"Structure invalid ({failed_count}/{total_filters} filters failing): {'; '.join(failure_reasons[:3])}",
            risk_score=risk_score,
        )


# ==================== Algo Alert Evaluator ====================

class AlgoAlertEvaluator(BaseEvaluator):
    """
    Pluggable evaluator for algo-alerts.

    Follows BaseEvaluator pattern. Runs in the fast loop (structured filters
    are deterministic and cheap — no AI required).

    Evaluation flow:
    1. Run FilterEngine against market data
    2. Check for regime conflict (oscillation detection)
    3. Mode A + all pass → ConvexityGate → StructureProposer → publish proposal
    4. Mode B + filters indicate invalid → ManagementAssessor → publish recommendation
    5. Every evaluation publishes filter state (transparency)
    """

    def __init__(self, redis=None, logger=None):
        self._redis = redis
        self._logger = logger
        self._filter_engine = FilterEngine()
        self._convexity_gate = ConvexityGate()
        self._structure_proposer = StructureProposer()
        self._management_assessor = ManagementAssessor()

        # Per-alert evaluation state tracking
        self._alert_states: Dict[str, AlgoAlertState] = {}

        # Default proposal TTL: 5 minutes
        self.proposal_ttl_seconds = 300

    @property
    def alert_type(self) -> str:
        return "algo_alert"

    @property
    def is_ai_powered(self) -> bool:
        return False  # Fast loop — structured filters only

    def _log(self, msg: str, level: str = "info", emoji: str = ""):
        if self._logger:
            fn = getattr(self._logger, level, self._logger.info)
            if emoji:
                fn(msg, emoji=emoji)
            else:
                fn(msg)

    def _get_state(self, alert_id: str) -> AlgoAlertState:
        """Get or create tracking state for an alert."""
        if alert_id not in self._alert_states:
            self._alert_states[alert_id] = AlgoAlertState(alert_id=alert_id)
        return self._alert_states[alert_id]

    def _detect_oscillation(self, state: AlgoAlertState, current_passed: bool) -> bool:
        """
        Detect filter oscillation (regime conflict).

        If filters oscillate (pass/fail/pass within N eval cycles), the alert
        should enter FROZEN state. This prevents oscillating proposals.
        """
        state.recent_pass_results.append(current_passed)
        if len(state.recent_pass_results) > AlgoAlertState.MAX_HISTORY:
            state.recent_pass_results = state.recent_pass_results[-AlgoAlertState.MAX_HISTORY:]

        if len(state.recent_pass_results) < 3:
            return False

        # Count state changes in recent history
        changes = 0
        for i in range(1, len(state.recent_pass_results)):
            if state.recent_pass_results[i] != state.recent_pass_results[i - 1]:
                changes += 1

        return changes >= AlgoAlertState.OSCILLATION_THRESHOLD

    def _check_stable_resume(self, state: AlgoAlertState) -> bool:
        """
        Check if a frozen alert has stabilized enough to resume.

        Requires N consecutive consistent results.
        """
        if len(state.recent_pass_results) < AlgoAlertState.STABLE_RESUME_THRESHOLD:
            return False

        recent = state.recent_pass_results[-AlgoAlertState.STABLE_RESUME_THRESHOLD:]
        return len(set(recent)) == 1  # All same value

    async def evaluate_algo_alert(
        self,
        algo_alert: dict,
        market_data: dict,
    ) -> Optional[dict]:
        """
        Evaluate a single algo alert against market data.

        Args:
            algo_alert: Dict with alert definition from database
            market_data: Current market data snapshot

        Returns:
            Dict with evaluation result and any proposal, or None on error
        """
        alert_id = algo_alert.get("id", "")
        mode = algo_alert.get("mode", "entry")
        status = algo_alert.get("status", "active")
        state = self._get_state(alert_id)

        # Parse filters from JSON
        filters_raw = algo_alert.get("filters", [])
        if isinstance(filters_raw, str):
            try:
                filters_raw = json.loads(filters_raw)
            except json.JSONDecodeError:
                filters_raw = []

        filters = []
        for f in filters_raw:
            filters.append(FilterCondition(
                id=f.get("id", str(uuid.uuid4())),
                data_source=f.get("dataSource", f.get("data_source", "")),
                field=f.get("field", ""),
                operator=f.get("operator", "gt"),
                value=f.get("value", 0),
                required=f.get("required", True),
            ))

        # Step 1: Run FilterEngine
        all_passed, filter_results = self._filter_engine.evaluate(filters, market_data)

        # Step 2: Oscillation detection
        is_oscillating = self._detect_oscillation(state, all_passed)

        result = {
            "algoAlertId": alert_id,
            "filterResults": [
                {
                    "filterId": r.filter_id,
                    "dataSource": r.data_source,
                    "field": r.field,
                    "passed": r.passed,
                    "currentValue": r.current_value,
                    "targetValue": r.target_value,
                    "dataAvailable": r.data_available,
                }
                for r in filter_results
            ],
            "allPassed": all_passed,
            "evaluatedAt": datetime.now(UTC).isoformat(),
            "proposal": None,
            "statusChange": None,
        }

        # Handle frozen state
        if status == "frozen":
            if self._check_stable_resume(state):
                state.frozen_cycles = 0
                state.stable_cycles = 0
                result["statusChange"] = {
                    "newStatus": "active",
                    "reason": "Regime stabilized — resuming evaluation",
                }
                self._log(f"Algo alert {alert_id} unfrozen — regime stabilized")
            else:
                state.frozen_cycles += 1
                result["status"] = "frozen"
                result["frozenReason"] = algo_alert.get("frozen_reason", "Conflicting structure — standing down")
                return result

        # Check for new oscillation → freeze
        if is_oscillating and status == "active":
            reason = "Conflicting structure detected — filters oscillating, standing down"
            result["statusChange"] = {
                "newStatus": "frozen",
                "reason": reason,
            }
            state.frozen_cycles = 1
            self._log(f"Algo alert {alert_id} frozen — oscillating filters")
            return result

        # Step 3: Mode-specific evaluation
        if mode == "entry" and all_passed:
            # Check for pending proposal dedup
            if state.pending_proposal_id:
                # Don't generate new proposal while one is pending
                return result

            # ConvexityGate
            constraints_raw = algo_alert.get("entry_constraints") or algo_alert.get("entryConstraints")
            if isinstance(constraints_raw, str):
                try:
                    constraints_raw = json.loads(constraints_raw)
                except json.JSONDecodeError:
                    constraints_raw = None

            gate_result = self._convexity_gate.check(market_data, constraints_raw)
            if not gate_result.feasible:
                self._log(f"Algo alert {alert_id}: convexity gate failed — {gate_result.reason}")
                result["gateResult"] = {"feasible": False, "reason": gate_result.reason}
                return result

            # StructureProposer
            suggested = self._structure_proposer.propose(market_data, constraints_raw)
            if suggested is None:
                self._log(f"Algo alert {alert_id}: no valid structure found — silence")
                return result

            # Generate proposal
            proposal_id = str(uuid.uuid4())
            now = datetime.now(UTC)
            expires_at = now + timedelta(seconds=self.proposal_ttl_seconds)

            # Calculate structural alignment score from filter pass rates
            passed_count = sum(1 for r in filter_results if r.passed)
            alignment_score = (passed_count / len(filter_results) * 100) if filter_results else 0

            result["proposal"] = {
                "id": proposal_id,
                "algoAlertId": alert_id,
                "userId": algo_alert.get("user_id", algo_alert.get("userId", 0)),
                "type": "entry",
                "status": "pending",
                "suggestedPosition": {
                    "strategyType": suggested.strategy_type,
                    "strike": suggested.strike,
                    "width": suggested.width,
                    "side": suggested.side,
                    "dte": suggested.dte,
                    "expiration": suggested.expiration,
                    "estimatedDebit": suggested.estimated_debit,
                    "symbol": suggested.symbol,
                },
                "reasoning": f"All {len(filters)} filters passing. {gate_result.reason}",
                "filterResults": result["filterResults"],
                "structuralAlignmentScore": alignment_score,
                "createdAt": now.isoformat(),
                "expiresAt": expires_at.isoformat(),
            }

            state.pending_proposal_id = proposal_id
            state.last_proposal_at = time.time()

        elif mode == "management" and not all_passed:
            # ManagementAssessor
            recommendation = self._management_assessor.assess(
                filter_results, market_data
            )

            if recommendation.action != "hold":
                proposal_id = str(uuid.uuid4())
                now = datetime.now(UTC)
                expires_at = now + timedelta(seconds=self.proposal_ttl_seconds)

                result["proposal"] = {
                    "id": proposal_id,
                    "algoAlertId": alert_id,
                    "userId": algo_alert.get("user_id", algo_alert.get("userId", 0)),
                    "type": recommendation.action,
                    "status": "pending",
                    "suggestedPosition": None,
                    "reasoning": recommendation.reasoning,
                    "filterResults": result["filterResults"],
                    "structuralAlignmentScore": 100 - recommendation.risk_score,
                    "createdAt": now.isoformat(),
                    "expiresAt": expires_at.isoformat(),
                }

        return result

    async def evaluate(self, alert, market_data: dict) -> AlertEvaluation:
        """
        BaseEvaluator interface — not used directly for algo alerts.

        Algo alerts are evaluated via evaluate_algo_alert() which is called
        from the alert engine's fast loop with the full algo alert dict.

        This stub exists to satisfy the ABC contract.
        """
        return AlertEvaluation(
            alert_id=getattr(alert, "id", ""),
            should_trigger=False,
            confidence=0.0,
            reasoning="Algo alerts use evaluate_algo_alert() — this stub should not be called directly",
        )

    def clear_pending_proposal(self, alert_id: str) -> None:
        """Clear the pending proposal for an alert (called when proposal is resolved)."""
        state = self._get_state(alert_id)
        state.pending_proposal_id = None
