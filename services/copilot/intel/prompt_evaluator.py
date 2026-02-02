# services/copilot/intel/prompt_evaluator.py
"""
PromptDrivenEvaluator - AI-powered prompt alert evaluation.

Evaluates prompt alerts against reference state using AI to:
1. Compare current state to reference
2. Determine if deviation matches prompt intent
3. Decide stage transitions (watching -> update -> warn -> accomplished)
"""

import json
import time
import hashlib
from datetime import datetime, UTC
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

from .alert_engine import BaseEvaluator, AlertEvaluation
from .ai_providers import AIProviderManager, AIMessage
from .reference_state_capture import ReferenceStateCaptureService, CapturedState


@dataclass
class PromptAlert:
    """Internal representation of a prompt alert for evaluation."""
    id: str
    user_id: int
    strategy_id: str
    prompt_text: str
    prompt_version: int
    parsed_reference_logic: Optional[Dict[str, Any]]
    parsed_deviation_logic: Optional[Dict[str, Any]]
    parsed_evaluation_mode: Optional[str]
    parsed_stage_thresholds: Optional[Dict[str, Any]]
    confidence_threshold: str
    orchestration_mode: str
    lifecycle_state: str
    current_stage: str
    last_ai_confidence: Optional[float]
    last_ai_reasoning: Optional[str]

    @classmethod
    def from_dict(cls, data: dict) -> "PromptAlert":
        """Create PromptAlert from database dict."""
        def get(key: str, default=None):
            # Try snake_case first, then camelCase
            snake = key
            camel = "".join(
                word.capitalize() if i > 0 else word
                for i, word in enumerate(key.split("_"))
            )
            return data.get(snake, data.get(camel, default))

        # Parse JSON fields
        def parse_json(val):
            if val is None:
                return None
            if isinstance(val, dict):
                return val
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return None

        return cls(
            id=data["id"],
            user_id=int(get("user_id", 0)),
            strategy_id=get("strategy_id", ""),
            prompt_text=get("prompt_text", ""),
            prompt_version=int(get("prompt_version", 1)),
            parsed_reference_logic=parse_json(get("parsed_reference_logic")),
            parsed_deviation_logic=parse_json(get("parsed_deviation_logic")),
            parsed_evaluation_mode=get("parsed_evaluation_mode"),
            parsed_stage_thresholds=parse_json(get("parsed_stage_thresholds")),
            confidence_threshold=get("confidence_threshold", "medium"),
            orchestration_mode=get("orchestration_mode", "parallel"),
            lifecycle_state=get("lifecycle_state", "active"),
            current_stage=get("current_stage", "watching"),
            last_ai_confidence=get("last_ai_confidence"),
            last_ai_reasoning=get("last_ai_reasoning"),
        )


@dataclass
class PromptEvaluation:
    """Result of evaluating a prompt alert."""
    alert_id: str
    should_transition: bool
    new_stage: Optional[str]  # watching, update, warn, accomplished
    confidence: float
    reasoning: str
    deviations: Dict[str, Any]
    timestamp: float
    provider: Optional[str] = None
    model: Optional[str] = None
    tokens_used: Optional[int] = None
    latency_ms: Optional[float] = None
    cached: bool = False


class PromptDrivenEvaluator(BaseEvaluator):
    """
    AI-powered evaluator for prompt-driven strategy alerts.

    Uses natural language understanding to evaluate if a strategy's
    current state deviates from the reference in ways the trader cares about.
    """

    # Confidence thresholds for stage transitions
    CONFIDENCE_THRESHOLDS = {
        "high": 0.8,
        "medium": 0.6,
        "low": 0.4,
    }

    # Cache TTL by evaluation mode (seconds)
    CACHE_TTL = {
        "regular": 30,
        "threshold": 60,
        "event": 300,
    }

    def __init__(
        self,
        ai_manager: Optional[AIProviderManager] = None,
        reference_service: Optional[ReferenceStateCaptureService] = None,
        logger=None,
    ):
        self._ai_manager = ai_manager
        self._reference_service = reference_service or ReferenceStateCaptureService(logger)
        self._logger = logger
        self._eval_cache: Dict[str, Tuple[PromptEvaluation, float]] = {}

    def _log(self, msg: str, level: str = "info"):
        if self._logger:
            fn = getattr(self._logger, level, self._logger.info)
            fn(msg)

    @property
    def alert_type(self) -> str:
        return "prompt_driven"

    @property
    def is_ai_powered(self) -> bool:
        return True

    async def evaluate(self, alert: Any, market_data: dict) -> AlertEvaluation:
        """
        Evaluate a prompt alert - implements BaseEvaluator interface.

        Note: This method is for compatibility with AlertEngine.
        Use evaluate_prompt for full prompt alert evaluation.
        """
        # Convert to PromptAlert if needed
        if isinstance(alert, dict):
            prompt_alert = PromptAlert.from_dict(alert)
        elif hasattr(alert, 'prompt_text'):
            prompt_alert = alert
        else:
            return AlertEvaluation(
                alert_id=getattr(alert, 'id', 'unknown'),
                should_trigger=False,
                confidence=0.0,
                reasoning="Invalid alert type for prompt evaluation",
            )

        # Get strategy data from market_data
        strategies = market_data.get("strategies", {})
        strategy_data = strategies.get(prompt_alert.strategy_id, {})

        # Get reference state from market_data (should be pre-fetched by engine)
        reference_data = market_data.get("reference_states", {}).get(prompt_alert.id, {})

        result = await self.evaluate_prompt(
            prompt_alert,
            strategy_data,
            reference_data,
            market_data,
        )

        # Convert PromptEvaluation to AlertEvaluation for compatibility
        return AlertEvaluation(
            alert_id=result.alert_id,
            should_trigger=result.should_transition,
            confidence=result.confidence,
            reasoning=result.reasoning,
            timestamp=result.timestamp,
            provider=result.provider,
            model=result.model,
            tokens_used=result.tokens_used,
            latency_ms=result.latency_ms,
        )

    async def evaluate_prompt(
        self,
        alert: PromptAlert,
        strategy_data: Dict[str, Any],
        reference_data: Dict[str, Any],
        market_data: Dict[str, Any],
    ) -> PromptEvaluation:
        """
        Evaluate a prompt alert against reference state.

        Args:
            alert: The prompt alert to evaluate
            strategy_data: Current strategy state
            reference_data: Reference state snapshot data
            market_data: Current market context

        Returns:
            PromptEvaluation with stage transition decision
        """
        # Skip if not active
        if alert.lifecycle_state != "active":
            return PromptEvaluation(
                alert_id=alert.id,
                should_transition=False,
                new_stage=None,
                confidence=0.0,
                reasoning=f"Alert is {alert.lifecycle_state}, not active",
                deviations={},
                timestamp=time.time(),
            )

        # Check evaluation mode - should we evaluate now?
        if not self._should_evaluate(alert, strategy_data, market_data):
            return PromptEvaluation(
                alert_id=alert.id,
                should_transition=False,
                new_stage=None,
                confidence=0.0,
                reasoning="Evaluation skipped based on evaluation mode",
                deviations={},
                timestamp=time.time(),
            )

        # Build current state
        current_state = await self._reference_service.capture_for_alert(
            alert.id, alert.strategy_id, strategy_data, market_data
        )

        # Build reference state from data
        reference_state = CapturedState(
            delta=reference_data.get("delta"),
            gamma=reference_data.get("gamma"),
            theta=reference_data.get("theta"),
            expiration_breakevens=self._parse_json(reference_data.get("expiration_breakevens")),
            theoretical_breakevens=self._parse_json(reference_data.get("theoretical_breakevens")),
            max_profit=reference_data.get("max_profit"),
            max_loss=reference_data.get("max_loss"),
            pnl_at_spot=reference_data.get("pnl_at_spot"),
            spot_price=reference_data.get("spot_price"),
            vix=reference_data.get("vix"),
            market_regime=reference_data.get("market_regime"),
            dte=reference_data.get("dte"),
            debit=reference_data.get("debit"),
            strike=reference_data.get("strike"),
            width=reference_data.get("width"),
            side=reference_data.get("side"),
            captured_at=reference_data.get("captured_at", ""),
        )

        # Check cache
        cache_key = self._compute_cache_key(alert, current_state, reference_state)
        cached = self._check_cache(cache_key, alert.parsed_evaluation_mode or "regular")
        if cached:
            self._log(f"Using cached evaluation for alert {alert.id}")
            return cached

        # Compute deviations
        deviations = self._reference_service.compute_deviation(reference_state, current_state)

        # Skip if minimal change (cost optimization)
        if self._reference_service.should_skip_evaluation(reference_state, current_state):
            result = PromptEvaluation(
                alert_id=alert.id,
                should_transition=False,
                new_stage=None,
                confidence=0.0,
                reasoning="Minimal change from reference - evaluation skipped",
                deviations=deviations,
                timestamp=time.time(),
            )
            self._update_cache(cache_key, result, alert.parsed_evaluation_mode or "regular")
            return result

        # AI evaluation
        if not self._ai_manager:
            return self._rule_based_evaluation(alert, deviations)

        result = await self._ai_evaluate(alert, current_state, reference_state, deviations, market_data)
        self._update_cache(cache_key, result, alert.parsed_evaluation_mode or "regular")

        return result

    def _should_evaluate(
        self,
        alert: PromptAlert,
        strategy_data: Dict[str, Any],
        market_data: Dict[str, Any],
    ) -> bool:
        """Check if we should evaluate based on evaluation mode."""
        mode = alert.parsed_evaluation_mode or "regular"

        if mode == "regular":
            return True

        if mode == "threshold":
            # Only evaluate if a specific metric crossed a threshold
            # This would be tracked externally and passed in market_data
            threshold_crossed = market_data.get("threshold_crossed", {})
            return alert.id in threshold_crossed

        if mode == "event":
            # Only evaluate on specific events
            events = market_data.get("events", [])
            relevant_events = ["trade_close", "dte_change", "position_adjust"]
            return any(e in events for e in relevant_events)

        return True

    async def _ai_evaluate(
        self,
        alert: PromptAlert,
        current: CapturedState,
        reference: CapturedState,
        deviations: Dict[str, Any],
        market_data: Dict[str, Any],
    ) -> PromptEvaluation:
        """Perform AI-powered evaluation."""
        system_prompt = self._get_system_prompt()
        user_prompt = self._build_evaluation_prompt(alert, current, reference, deviations)

        try:
            start_time = time.time()
            response = await self._ai_manager.generate(
                messages=[AIMessage(role="user", content=user_prompt)],
                system_prompt=system_prompt,
                max_tokens=512,
                temperature=0.2,
            )
            latency_ms = (time.time() - start_time) * 1000

            result = self._parse_ai_response(alert, response.content, deviations)
            result.provider = response.provider.value
            result.model = response.model
            result.tokens_used = response.tokens_used
            result.latency_ms = latency_ms

            return result

        except Exception as e:
            self._log(f"AI evaluation error: {e}", level="warn")
            return self._rule_based_evaluation(alert, deviations)

    def _get_system_prompt(self) -> str:
        return """You are evaluating a trader's prompt-driven alert against current market conditions.

The trader has described what they want to be alerted about in natural language. Your job is to:
1. Compare the current state to the reference state
2. Determine if the deviation matches what the trader cares about
3. Decide the appropriate stage transition

Stage flow: watching -> update -> warn -> accomplished
- watching: passively monitoring, no significant deviation
- update: change detected, informational (e.g., "gamma up 30% from entry")
- warn: approaching critical threshold (e.g., "profit at 45% of max")
- accomplished: objective met or protection triggered

You must respond with ONLY a valid JSON object:
{
    "should_transition": boolean,
    "new_stage": "watching" | "update" | "warn" | "accomplished" | null,
    "confidence": number (0.0-1.0),
    "reasoning": "Brief explanation matching the trader's language",
    "key_deviation": "The most important metric change"
}

Important:
- Match your reasoning to the trader's original language/intent
- Only transition if the deviation is meaningful to what they asked for
- accomplished means the alert's objective is fully met (not just triggered)
- Be conservative with warn stage - only when action might be needed soon"""

    def _build_evaluation_prompt(
        self,
        alert: PromptAlert,
        current: CapturedState,
        reference: CapturedState,
        deviations: Dict[str, Any],
    ) -> str:
        """Build the evaluation prompt."""
        deviations_str = json.dumps(deviations, indent=2, default=str)

        return f"""Evaluate this prompt alert:

TRADER'S ORIGINAL PROMPT:
"{alert.prompt_text}"

PARSED DEVIATION LOGIC:
{json.dumps(alert.parsed_deviation_logic, indent=2) if alert.parsed_deviation_logic else "Not parsed"}

PARSED STAGE THRESHOLDS:
{json.dumps(alert.parsed_stage_thresholds, indent=2) if alert.parsed_stage_thresholds else "Not parsed"}

CURRENT STAGE: {alert.current_stage}

REFERENCE STATE (captured at {reference.captured_at}):
- Delta: {reference.delta}
- Gamma: {reference.gamma}
- Theta: {reference.theta}
- Max Profit: ${reference.max_profit:.2f if reference.max_profit else 'N/A'}
- PnL at Spot: ${reference.pnl_at_spot:.2f if reference.pnl_at_spot else 'N/A'}
- Spot: {reference.spot_price}
- DTE: {reference.dte}

CURRENT STATE:
- Delta: {current.delta}
- Gamma: {current.gamma}
- Theta: {current.theta}
- Max Profit: ${current.max_profit:.2f if current.max_profit else 'N/A'}
- PnL at Spot: ${current.pnl_at_spot:.2f if current.pnl_at_spot else 'N/A'}
- Spot: {current.spot_price}
- DTE: {current.dte}

COMPUTED DEVIATIONS:
{deviations_str}

Based on the trader's intent and the computed deviations, should we transition to a new stage?"""

    def _parse_ai_response(
        self,
        alert: PromptAlert,
        content: str,
        deviations: Dict[str, Any],
    ) -> PromptEvaluation:
        """Parse AI response into PromptEvaluation."""
        try:
            content = content.strip()

            # Handle markdown code blocks
            if content.startswith("```"):
                lines = content.split("\n")
                end_idx = len(lines) - 1
                for i in range(1, len(lines)):
                    if lines[i].startswith("```"):
                        end_idx = i
                        break
                content = "\n".join(lines[1:end_idx])

            data = json.loads(content)

            # Check confidence against threshold
            confidence = float(data.get("confidence", 0.5))
            threshold = self.CONFIDENCE_THRESHOLDS.get(alert.confidence_threshold, 0.6)

            should_transition = data.get("should_transition", False)
            new_stage = data.get("new_stage")

            # Don't transition if confidence below threshold
            if should_transition and confidence < threshold:
                should_transition = False
                new_stage = None

            return PromptEvaluation(
                alert_id=alert.id,
                should_transition=should_transition,
                new_stage=new_stage,
                confidence=confidence,
                reasoning=data.get("reasoning", "No reasoning provided"),
                deviations=deviations,
                timestamp=time.time(),
            )

        except (json.JSONDecodeError, KeyError) as e:
            self._log(f"Failed to parse AI response: {e}", level="warn")
            return self._rule_based_evaluation(alert, deviations)

    def _rule_based_evaluation(
        self,
        alert: PromptAlert,
        deviations: Dict[str, Any],
    ) -> PromptEvaluation:
        """Fallback rule-based evaluation when AI fails."""
        # Simple heuristics based on deviations
        should_transition = False
        new_stage = None
        reasoning = "Rule-based evaluation (AI unavailable)"

        # Check gamma deviation
        gamma_dev = deviations.get("gamma", {})
        if abs(gamma_dev.get("pct_change", 0)) > 30:
            if alert.current_stage == "watching":
                should_transition = True
                new_stage = "update"
                reasoning = f"Gamma changed by {gamma_dev.get('pct_change', 0):.1f}%"

        # Check profit percentage deviation
        profit_dev = deviations.get("profit_percentage", {})
        if profit_dev.get("current", 100) < 50 and alert.current_stage in ["watching", "update"]:
            should_transition = True
            new_stage = "warn"
            reasoning = f"Profit at {profit_dev.get('current', 0):.1f}% of max"

        if profit_dev.get("current", 100) < 30:
            should_transition = True
            new_stage = "accomplished"
            reasoning = f"Protection threshold reached - profit at {profit_dev.get('current', 0):.1f}%"

        return PromptEvaluation(
            alert_id=alert.id,
            should_transition=should_transition,
            new_stage=new_stage,
            confidence=0.5,
            reasoning=reasoning,
            deviations=deviations,
            timestamp=time.time(),
        )

    def _compute_cache_key(
        self,
        alert: PromptAlert,
        current: CapturedState,
        reference: CapturedState,
    ) -> str:
        """Compute cache key based on context."""
        # Hash key components
        key_parts = [
            alert.id,
            str(alert.prompt_version),
            str(current.delta),
            str(current.gamma),
            str(current.pnl_at_spot),
            str(current.spot_price),
            str(current.dte),
        ]
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()

    def _check_cache(self, key: str, mode: str) -> Optional[PromptEvaluation]:
        """Check if we have a cached evaluation."""
        if key not in self._eval_cache:
            return None

        cached, timestamp = self._eval_cache[key]
        ttl = self.CACHE_TTL.get(mode, 30)

        if time.time() - timestamp > ttl:
            del self._eval_cache[key]
            return None

        cached.cached = True
        return cached

    def _update_cache(self, key: str, result: PromptEvaluation, mode: str):
        """Update evaluation cache."""
        self._eval_cache[key] = (result, time.time())

        # Clean old entries if cache grows too large
        if len(self._eval_cache) > 1000:
            current_time = time.time()
            self._eval_cache = {
                k: v for k, v in self._eval_cache.items()
                if current_time - v[1] < 300  # Keep entries less than 5 min old
            }

    def _parse_json(self, val: Any) -> Any:
        """Parse JSON string if needed."""
        if val is None:
            return None
        if isinstance(val, (list, dict)):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
