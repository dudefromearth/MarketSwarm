# services/copilot/intel/alert_evaluators.py
"""
Alert Evaluators - Pluggable evaluation strategies.

Contains evaluators for each alert type:
- PriceEvaluator: Simple spot price comparison
- DebitEvaluator: Strategy debit comparison
- ProfitTargetEvaluator: Profit target check
- TrailingStopEvaluator: Trailing stop with high water mark
- AIThetaGammaEvaluator: AI-powered dynamic risk zone evaluation
"""

import json
import time
from typing import Optional

from .alert_engine import Alert, AlertEvaluation, BaseEvaluator
from .ai_providers import AIProviderManager, AIMessage


class PriceEvaluator(BaseEvaluator):
    """
    Evaluates price alerts - spot price crosses a target level.
    No AI required, evaluates instantly.
    """

    @property
    def alert_type(self) -> str:
        return "price"

    @property
    def is_ai_powered(self) -> bool:
        return False

    async def evaluate(self, alert: Alert, market_data: dict) -> AlertEvaluation:
        spot = market_data.get("spot_price") or market_data.get("spot")
        if spot is None:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning="No spot price available",
            )

        condition_met = self._check_condition(alert.condition, spot, alert.target_value)

        # For repeat alerts, check if price crossed from other side
        if alert.behavior == "repeat" and condition_met:
            if not alert.was_on_other_side:
                condition_met = False
            # Note: was_on_other_side will be reset by engine after trigger

        return AlertEvaluation(
            alert_id=alert.id,
            should_trigger=condition_met,
            confidence=1.0 if condition_met else 0.0,
            reasoning=f"Spot {spot:.2f} {'crossed' if condition_met else 'has not crossed'} {alert.target_value:.2f} ({alert.condition})",
        )

    def _check_condition(self, condition: str, value: float, target: float) -> bool:
        """Check if condition is met."""
        if condition == "above":
            return value > target
        elif condition == "below":
            return value < target
        elif condition == "at":
            # Within 0.1% of target
            return abs(value - target) / target < 0.001
        return False


class DebitEvaluator(BaseEvaluator):
    """
    Evaluates debit alerts - strategy debit crosses a target level.
    No AI required.
    """

    @property
    def alert_type(self) -> str:
        return "debit"

    @property
    def is_ai_powered(self) -> bool:
        return False

    async def evaluate(self, alert: Alert, market_data: dict) -> AlertEvaluation:
        # Get strategy debit from market data
        strategies = market_data.get("strategies", {})
        strategy = strategies.get(alert.strategy_id, {})
        current_debit = strategy.get("current_debit") or strategy.get("debit")

        if current_debit is None:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning=f"No debit data for strategy {alert.strategy_id}",
            )

        condition_met = self._check_condition(alert.condition, current_debit, alert.target_value)

        return AlertEvaluation(
            alert_id=alert.id,
            should_trigger=condition_met,
            confidence=1.0 if condition_met else 0.0,
            reasoning=f"Debit ${current_debit:.2f} {'crossed' if condition_met else 'has not crossed'} ${alert.target_value:.2f} ({alert.condition})",
        )

    def _check_condition(self, condition: str, value: float, target: float) -> bool:
        """Check if condition is met."""
        if condition == "above":
            return value > target
        elif condition == "below":
            return value < target
        elif condition == "at":
            return abs(value - target) / target < 0.001 if target != 0 else value == 0
        return False


class ProfitTargetEvaluator(BaseEvaluator):
    """
    Evaluates profit target alerts.
    Triggers when position profit reaches target percentage.
    No AI required.
    """

    @property
    def alert_type(self) -> str:
        return "profit_target"

    @property
    def is_ai_powered(self) -> bool:
        return False

    async def evaluate(self, alert: Alert, market_data: dict) -> AlertEvaluation:
        # Get strategy data
        strategies = market_data.get("strategies", {})
        strategy = strategies.get(alert.strategy_id, {})
        current_debit = strategy.get("current_debit") or strategy.get("debit")
        entry_debit = alert.entry_debit or strategy.get("entry_debit")

        if current_debit is None or entry_debit is None:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning="Missing debit data for profit calculation",
            )

        # Calculate profit as percentage of entry
        # For credit spreads, profit = entry - current (when current goes down)
        # For debit spreads, profit = current - entry (when current goes up)
        profit_pct = (entry_debit - current_debit) / entry_debit if entry_debit != 0 else 0
        target_pct = alert.target_value

        condition_met = profit_pct >= target_pct

        return AlertEvaluation(
            alert_id=alert.id,
            should_trigger=condition_met,
            confidence=1.0 if condition_met else 0.0,
            reasoning=f"Profit {profit_pct*100:.1f}% {'reached' if condition_met else 'below'} target {target_pct*100:.1f}%",
        )


class TrailingStopEvaluator(BaseEvaluator):
    """
    Evaluates trailing stop alerts.
    Triggers when price drops specified amount from high water mark.
    No AI required.
    """

    @property
    def alert_type(self) -> str:
        return "trailing_stop"

    @property
    def is_ai_powered(self) -> bool:
        return False

    async def evaluate(self, alert: Alert, market_data: dict) -> AlertEvaluation:
        # Get strategy data
        strategies = market_data.get("strategies", {})
        strategy = strategies.get(alert.strategy_id, {})
        current_debit = strategy.get("current_debit") or strategy.get("debit")
        entry_debit = alert.entry_debit or strategy.get("entry_debit")

        if current_debit is None or entry_debit is None:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning="Missing debit data for trailing stop",
            )

        # Calculate current profit
        profit = entry_debit - current_debit

        # Update high water mark if new high
        high_water_mark = alert.high_water_mark_profit or 0
        if profit > high_water_mark:
            # This will be persisted by the engine
            alert.high_water_mark_profit = profit
            high_water_mark = profit

        # Calculate drawdown from high water mark
        drawdown = high_water_mark - profit if high_water_mark > 0 else 0
        stop_amount = alert.target_value

        # Trigger if drawdown exceeds stop amount
        condition_met = drawdown >= stop_amount and high_water_mark > 0

        return AlertEvaluation(
            alert_id=alert.id,
            should_trigger=condition_met,
            confidence=1.0 if condition_met else 0.0,
            reasoning=f"Drawdown ${drawdown:.2f} from HWM ${high_water_mark:.2f} {'exceeded' if condition_met else 'below'} stop ${stop_amount:.2f}",
        )


class AIThetaGammaEvaluator(BaseEvaluator):
    """
    AI-powered theta/gamma zone evaluation.
    Uses AI to analyze position Greeks and market conditions
    to determine safe profit zone boundaries.
    """

    def __init__(self, ai_manager: Optional[AIProviderManager] = None):
        self._ai_manager = ai_manager

    @property
    def alert_type(self) -> str:
        return "ai_theta_gamma"

    @property
    def is_ai_powered(self) -> bool:
        return True

    async def evaluate(self, alert: Alert, market_data: dict) -> AlertEvaluation:
        if not self._ai_manager:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning="AI manager not configured",
            )

        # Build prompt with market context
        prompt = self._build_prompt(alert, market_data)

        try:
            start_time = time.time()
            response = await self._ai_manager.generate(
                messages=[AIMessage(role="user", content=prompt)],
                system_prompt=self._get_system_prompt(),
                max_tokens=512,
                temperature=0.3,
            )
            latency_ms = (time.time() - start_time) * 1000

            # Parse AI response
            result = self._parse_response(alert.id, response.content)
            result.provider = response.provider.value
            result.model = response.model
            result.tokens_used = response.tokens_used
            result.latency_ms = latency_ms

            return result

        except Exception as e:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning=f"AI evaluation error: {str(e)}",
            )

    def _get_system_prompt(self) -> str:
        return """You are an options trading risk analyst. Analyze positions for theta decay and gamma risk.

Your task: Determine if the current market conditions put the position at risk of losing the minimum profit threshold.

You must respond with ONLY a valid JSON object (no markdown, no explanation outside JSON):
{
  "should_trigger": boolean,
  "confidence": number (0.0-1.0),
  "reasoning": "Brief explanation",
  "zone_low": number (price level where risk increases),
  "zone_high": number (price level where risk increases)
}

Consider:
- Theta decay accelerates closer to expiration
- Gamma risk increases near the money
- VIX impacts option prices
- GEX regime affects price movement patterns"""

    def _build_prompt(self, alert: Alert, market_data: dict) -> str:
        # Get strategy info from market data
        strategies = market_data.get("strategies", {})
        strategy = strategies.get(alert.strategy_id, {})

        spot = market_data.get("spot_price") or market_data.get("spot", "N/A")
        vix = market_data.get("vix", "N/A")
        gex_regime = market_data.get("gex_regime", "unknown")

        # Get strategy details
        current_debit = strategy.get("current_debit", strategy.get("debit", "N/A"))
        entry_debit = alert.entry_debit or strategy.get("entry_debit", "N/A")
        strike = strategy.get("strike", "N/A")
        width = strategy.get("width", "N/A")
        dte = strategy.get("dte", "N/A")
        side = strategy.get("side", "N/A")

        # Calculate current profit if possible
        profit_info = ""
        if isinstance(current_debit, (int, float)) and isinstance(entry_debit, (int, float)):
            profit = entry_debit - current_debit
            profit_pct = (profit / entry_debit * 100) if entry_debit != 0 else 0
            profit_info = f"Current Profit: ${profit:.2f} ({profit_pct:.1f}%)"

        return f"""Analyze this options position for theta decay and gamma risk:

Position: {alert.source.get('label', 'Unknown')}
Strategy Type: {strategy.get('type', 'vertical spread')}
Strike: {strike}
Width: {width}
Side: {side}
DTE: {dte}

Entry Debit: ${entry_debit}
Current Debit: ${current_debit}
{profit_info}
Min Profit Threshold: {(alert.min_profit_threshold or 0.5) * 100}%

Market Conditions:
- Current Spot: {spot}
- VIX: {vix}
- GEX Regime: {gex_regime}

Determine:
1. Is the position at immediate risk of falling below the profit threshold?
2. What are the safe zone boundaries (price levels where profit stays above threshold)?"""

    def _parse_response(self, alert_id: str, content: str) -> AlertEvaluation:
        """Parse AI response into AlertEvaluation."""
        try:
            # Try to extract JSON from response
            content = content.strip()

            # Handle markdown code blocks
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])

            data = json.loads(content)

            return AlertEvaluation(
                alert_id=alert_id,
                should_trigger=data.get("should_trigger", False),
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", "No reasoning provided"),
                zone_low=data.get("zone_low"),
                zone_high=data.get("zone_high"),
            )

        except (json.JSONDecodeError, KeyError) as e:
            # Fallback: try to extract meaning from text response
            content_lower = content.lower()
            should_trigger = any(
                word in content_lower
                for word in ["trigger", "risk", "danger", "exit", "close"]
            )

            return AlertEvaluation(
                alert_id=alert_id,
                should_trigger=should_trigger,
                confidence=0.3,
                reasoning=f"Could not parse AI response: {content[:200]}",
            )


class AISentimentEvaluator(BaseEvaluator):
    """
    AI-powered market sentiment evaluation.
    Analyzes market conditions to determine overall sentiment.
    """

    def __init__(self, ai_manager: Optional[AIProviderManager] = None):
        self._ai_manager = ai_manager

    @property
    def alert_type(self) -> str:
        return "ai_sentiment"

    @property
    def is_ai_powered(self) -> bool:
        return True

    async def evaluate(self, alert: Alert, market_data: dict) -> AlertEvaluation:
        if not self._ai_manager:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning="AI manager not configured",
            )

        # Build sentiment analysis prompt
        prompt = self._build_prompt(alert, market_data)

        try:
            response = await self._ai_manager.generate(
                messages=[AIMessage(role="user", content=prompt)],
                system_prompt=self._get_system_prompt(),
                max_tokens=256,
                temperature=0.3,
            )

            return self._parse_response(alert, response.content)

        except Exception as e:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning=f"AI sentiment error: {str(e)}",
            )

    def _get_system_prompt(self) -> str:
        return """You are a market sentiment analyst. Analyze market conditions and return a sentiment score.

Respond with ONLY a valid JSON object:
{
  "sentiment": number (-1.0 bearish to 1.0 bullish),
  "confidence": number (0.0-1.0),
  "reasoning": "Brief explanation"
}"""

    def _build_prompt(self, alert: Alert, market_data: dict) -> str:
        spot = market_data.get("spot_price") or market_data.get("spot", "N/A")
        vix = market_data.get("vix", "N/A")
        gex_regime = market_data.get("gex_regime", "unknown")
        bias_lfi = market_data.get("bias_lfi", {})

        return f"""Analyze current market sentiment:

Spot Price: {spot}
VIX: {vix}
GEX Regime: {gex_regime}
Bias: {bias_lfi.get('bias', 'N/A')}
Flow: {bias_lfi.get('flow', 'N/A')}

Provide sentiment score (-1 bearish to +1 bullish)."""

    def _parse_response(self, alert: Alert, content: str) -> AlertEvaluation:
        """Parse sentiment response."""
        try:
            content = content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])

            data = json.loads(content)
            sentiment = float(data.get("sentiment", 0))
            confidence = float(data.get("confidence", 0.5))

            # Check if sentiment matches alert threshold and direction
            threshold = getattr(alert, "sentiment_threshold", 0.5)
            direction = getattr(alert, "direction", "either")

            should_trigger = False
            if direction == "bullish" and sentiment >= threshold:
                should_trigger = True
            elif direction == "bearish" and sentiment <= -threshold:
                should_trigger = True
            elif direction == "either" and abs(sentiment) >= threshold:
                should_trigger = True

            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=should_trigger,
                confidence=confidence,
                reasoning=data.get("reasoning", f"Sentiment: {sentiment:.2f}"),
            )

        except Exception:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning=f"Could not parse sentiment response",
            )


class AIRiskZoneEvaluator(BaseEvaluator):
    """
    AI-powered risk zone evaluation.
    Identifies support/resistance/pivot zones.
    """

    def __init__(self, ai_manager: Optional[AIProviderManager] = None):
        self._ai_manager = ai_manager

    @property
    def alert_type(self) -> str:
        return "ai_risk_zone"

    @property
    def is_ai_powered(self) -> bool:
        return True

    async def evaluate(self, alert: Alert, market_data: dict) -> AlertEvaluation:
        if not self._ai_manager:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning="AI manager not configured",
            )

        prompt = self._build_prompt(alert, market_data)

        try:
            response = await self._ai_manager.generate(
                messages=[AIMessage(role="user", content=prompt)],
                system_prompt=self._get_system_prompt(),
                max_tokens=256,
                temperature=0.3,
            )

            return self._parse_response(alert, market_data, response.content)

        except Exception as e:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning=f"AI risk zone error: {str(e)}",
            )

    def _get_system_prompt(self) -> str:
        return """You are a technical analyst identifying key price zones.

Respond with ONLY a valid JSON object:
{
  "zone_low": number,
  "zone_high": number,
  "zone_type": "support" | "resistance" | "pivot",
  "confidence": number (0.0-1.0),
  "reasoning": "Brief explanation"
}"""

    def _build_prompt(self, alert: Alert, market_data: dict) -> str:
        spot = market_data.get("spot_price") or market_data.get("spot", "N/A")
        zero_gamma = market_data.get("zero_gamma", "N/A")
        gamma_magnet = market_data.get("gamma_magnet", "N/A")

        zone_type = getattr(alert, "zone_type", "pivot")

        return f"""Identify {zone_type} zone for current market:

Spot Price: {spot}
Zero Gamma: {zero_gamma}
Gamma Magnet: {gamma_magnet}

Find the nearest {zone_type} zone boundaries."""

    def _parse_response(self, alert: Alert, market_data: dict, content: str) -> AlertEvaluation:
        """Parse risk zone response."""
        try:
            content = content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])

            data = json.loads(content)
            zone_low = data.get("zone_low")
            zone_high = data.get("zone_high")
            confidence = float(data.get("confidence", 0.5))

            # Check if spot is outside the zone (trigger condition)
            spot = market_data.get("spot_price") or market_data.get("spot")
            should_trigger = False

            if spot and zone_low and zone_high:
                if alert.condition == "outside_zone":
                    should_trigger = spot < zone_low or spot > zone_high
                elif alert.condition == "inside_zone":
                    should_trigger = zone_low <= spot <= zone_high

            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=should_trigger,
                confidence=confidence,
                reasoning=data.get("reasoning", f"Zone: {zone_low}-{zone_high}"),
                zone_low=zone_low,
                zone_high=zone_high,
            )

        except Exception:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning="Could not parse risk zone response",
            )


def create_all_evaluators(ai_manager: Optional[AIProviderManager] = None) -> list:
    """
    Factory function to create all evaluators.

    Args:
        ai_manager: AI provider manager for AI-powered evaluators

    Returns:
        List of all evaluator instances
    """
    return [
        PriceEvaluator(),
        DebitEvaluator(),
        ProfitTargetEvaluator(),
        TrailingStopEvaluator(),
        AIThetaGammaEvaluator(ai_manager),
        AISentimentEvaluator(ai_manager),
        AIRiskZoneEvaluator(ai_manager),
    ]
