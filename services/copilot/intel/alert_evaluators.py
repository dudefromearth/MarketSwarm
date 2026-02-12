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


class ButterflyEntryEvaluator(BaseEvaluator):
    """
    Evaluates entry conditions for OTM butterfly options trading.
    Detects market support using GEX, Volume Profile, LIM, and Market Mode.
    Confirms reversal before triggering.
    No AI required, evaluates instantly (fast loop).
    """

    @property
    def alert_type(self) -> str:
        return "butterfly_entry"

    @property
    def is_ai_powered(self) -> bool:
        return False

    async def evaluate(self, alert: Alert, market_data: dict) -> AlertEvaluation:
        # Step 1: Check market mode (prefer compression)
        market_mode = market_data.get('market_mode', {}).get('score', 50)
        if market_mode > 50:  # Expansion mode - not ideal for butterflies
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning="Market in expansion mode (score > 50)",
            )

        # Step 2: Check Liquidity Intent Map
        bias_lfi = market_data.get('bias_lfi', {})
        lfi_score = bias_lfi.get('lfi_score', 50)
        directional = bias_lfi.get('directional_strength', 0)

        # Ideal: Absorbing (LFI > 50) + Not hostile (directional >= -30)
        if lfi_score < 50 or directional < -30:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning=f"Liquidity unfavorable: LFI={lfi_score}, directional={directional}",
            )

        # Step 3: Detect support from GEX + Volume Profile
        support = self._detect_support(market_data)
        if not support:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning="No support level detected near current price",
            )

        # Step 4: Confirm reversal
        reversal = self._confirm_reversal(support, market_data)
        if not reversal:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning=f"Support detected at {support['level']:.2f} ({support['type']}) but no reversal confirmed",
            )

        # Step 5: Calculate butterfly target
        butterfly = self._calculate_butterfly(support, market_data)

        # Calculate overall confidence
        confidence = support['strength'] * reversal['strength']

        return AlertEvaluation(
            alert_id=alert.id,
            should_trigger=True,
            confidence=confidence,
            reasoning=f"Entry signal: {support['type'].upper()} support at {support['level']:.2f}, {reversal['type']} reversal. Target: {butterfly['strike']} {butterfly['side']} butterfly, width {butterfly['width']}",
            entry_support_type=support['type'],
            entry_support_level=support['level'],
            entry_reversal_confirmed=True,
            entry_target_strike=butterfly['strike'],
            entry_target_width=butterfly['width'],
        )

    def _detect_support(self, market_data: dict) -> Optional[dict]:
        """Detect support from GEX and Volume Profile data."""
        spot = market_data.get('spot_price') or market_data.get('spot')
        if spot is None:
            return None

        tolerance = 5.0  # Points from support
        supports = []

        # GEX Support (strongest)
        gamma_levels = market_data.get('gamma_levels', [])
        for level in gamma_levels:
            net_gamma = level.get('net_gamma', 0)
            strike = level.get('strike')
            if net_gamma > 0 and strike and abs(spot - strike) <= tolerance:
                supports.append({'type': 'gex', 'level': strike, 'strength': 0.9})

        # Volume Profile
        vp = market_data.get('volume_profile', {})
        poc = vp.get('poc')
        if poc and abs(spot - poc) <= tolerance:
            supports.append({'type': 'poc', 'level': poc, 'strength': 0.85})

        val = vp.get('val')
        if val and abs(spot - val) <= tolerance:
            supports.append({'type': 'val', 'level': val, 'strength': 0.8})

        for hvn in vp.get('hvns', []):
            if abs(spot - hvn) <= tolerance:
                supports.append({'type': 'hvn', 'level': hvn, 'strength': 0.7})

        # Zero gamma pivot
        zero_gamma = market_data.get('zero_gamma')
        if zero_gamma and abs(spot - zero_gamma) <= tolerance:
            supports.append({'type': 'zero_gamma', 'level': zero_gamma, 'strength': 0.6})

        return max(supports, key=lambda s: s['strength']) if supports else None

    def _confirm_reversal(self, support: dict, market_data: dict) -> Optional[dict]:
        """Confirm reversal pattern from price history."""
        price_history = market_data.get('price_history', [])[-10:]
        spot = market_data.get('spot_price') or market_data.get('spot')

        if not price_history or spot is None:
            return None

        # Pattern 1: Bounce (touched support, now above)
        lows = [p.get('low', p.get('price', spot)) for p in price_history]
        if min(lows) <= support['level'] + 1 and spot > support['level'] + 3:
            return {'type': 'bounce', 'strength': 0.8}

        # Pattern 2: Higher lows forming
        if len(lows) >= 3 and lows[-1] > lows[-3] > support['level']:
            return {'type': 'higher_lows', 'strength': 0.7}

        return None

    def _calculate_butterfly(self, support: dict, market_data: dict) -> dict:
        """Calculate butterfly target based on gamma magnet or round numbers."""
        spot = market_data.get('spot_price') or market_data.get('spot')
        gamma_magnet = market_data.get('gamma_magnet')

        # Target the gamma magnet or next round number
        if gamma_magnet and gamma_magnet > spot:
            target = gamma_magnet
        else:
            target = round((spot + 15) / 5) * 5

        return {'side': 'call', 'strike': target, 'width': 10}


class ButterflyProfitMgmtEvaluator(BaseEvaluator):
    """
    AI-powered profit management for butterfly positions.
    Activates at 75% profit threshold, tracks high water mark,
    assesses risk of losing gains via theta/gamma.
    Slow loop (5s) with AI analysis.
    """

    def __init__(self, ai_manager: Optional[AIProviderManager] = None):
        self._ai_manager = ai_manager

    @property
    def alert_type(self) -> str:
        return "butterfly_profit_mgmt"

    @property
    def is_ai_powered(self) -> bool:
        return True

    async def evaluate(self, alert: Alert, market_data: dict) -> AlertEvaluation:
        # Get strategy data
        strategies = market_data.get("strategies", {})
        strategy = strategies.get(alert.strategy_id, {})
        current_debit = strategy.get("current_debit") or strategy.get("debit")
        entry_debit = alert.entry_debit or strategy.get("entry_debit")

        if current_debit is None or entry_debit is None or entry_debit == 0:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning="Missing debit data for profit management",
            )

        # Step 1: Check if activated (profit >= 75% of debit)
        profit_pct = (entry_debit - current_debit) / entry_debit
        activation_threshold = alert.mgmt_activation_threshold or 0.75

        if profit_pct < activation_threshold:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning=f"Profit {profit_pct*100:.1f}% below activation threshold {activation_threshold*100:.0f}%",
            )

        # Step 2: Update high water mark
        current_profit = entry_debit - current_debit
        hwm = alert.mgmt_high_water_mark or 0
        if current_profit > hwm:
            alert.mgmt_high_water_mark = current_profit
            hwm = current_profit

        # Step 3: Calculate risk score
        risk_score = self._calculate_risk_score(alert, strategy, market_data, hwm, current_profit)
        alert.mgmt_risk_score = risk_score

        # Step 4: Determine recommendation
        recommendation = self._get_recommendation(risk_score, hwm, current_profit)
        alert.mgmt_recommendation = recommendation

        # Step 5: Optionally use AI for nuanced assessment
        ai_reasoning = None
        if self._ai_manager and recommendation in ('EXIT', 'TIGHTEN'):
            ai_result = await self._get_ai_assessment(alert, strategy, market_data, risk_score, recommendation)
            if ai_result:
                ai_reasoning = ai_result.get('reasoning')
                # AI can override recommendation to EXIT if risk is extreme
                if ai_result.get('override_to_exit'):
                    recommendation = 'EXIT'
                    alert.mgmt_recommendation = recommendation

        alert.mgmt_last_assessment = market_data.get('timestamp') or ''

        # Step 6: Trigger if EXIT recommended
        should_trigger = recommendation == 'EXIT'

        reasoning = f"Risk score: {risk_score:.1f}/100, Recommendation: {recommendation}"
        if ai_reasoning:
            reasoning += f". AI: {ai_reasoning}"

        return AlertEvaluation(
            alert_id=alert.id,
            should_trigger=should_trigger,
            confidence=min(1.0, risk_score / 100),
            reasoning=reasoning,
            mgmt_risk_score=risk_score,
            mgmt_recommendation=recommendation,
            mgmt_high_water_mark=hwm,
        )

    def _calculate_risk_score(self, alert: Alert, strategy: dict, market_data: dict,
                               hwm: float, current_profit: float) -> float:
        """
        Calculate composite risk score (0-100).

        Weights:
        - Time Risk: 35%
        - Gamma Risk: 30%
        - Drawdown Risk: 20%
        - VIX Risk: 15%
        """
        dte = strategy.get('dte', alert.mgmt_initial_dte or 7)
        spot = market_data.get('spot_price') or market_data.get('spot', 0)
        strike = strategy.get('strike', 0)
        vix = market_data.get('vix', 15)

        # Time risk (0-100): accelerates as DTE -> 0
        if dte == 0:
            time_risk = 100
        else:
            time_risk = max(0, 100 - dte * 15)

        # Gamma risk (0-100): increases as spot -> strike
        if spot and strike:
            distance_pct = abs(spot - strike) / spot * 100 if spot != 0 else 0
            gamma_risk = max(0, 100 - distance_pct * 20)
        else:
            gamma_risk = 50  # Default if data missing

        # Drawdown risk (0-100): (HWM - current) / HWM
        if hwm > 0:
            drawdown_risk = ((hwm - current_profit) / hwm) * 100
        else:
            drawdown_risk = 0

        # VIX risk (0-100): VIX > 25 = elevated
        vix_risk = min(100, max(0, (vix - 15) * 5))

        # Weighted composite
        return (time_risk * 0.35 +
                gamma_risk * 0.30 +
                drawdown_risk * 0.20 +
                vix_risk * 0.15)

    def _get_recommendation(self, risk_score: float, hwm: float, current_profit: float) -> str:
        """Determine recommendation based on risk score and drawdown."""
        # 50% drawdown from HWM is immediate exit
        if hwm > 0 and current_profit < hwm * 0.5:
            return 'EXIT'

        if risk_score > 80:
            return 'EXIT'
        elif risk_score > 60:
            return 'TIGHTEN'
        else:
            return 'HOLD'

    async def _get_ai_assessment(self, alert: Alert, strategy: dict, market_data: dict,
                                  risk_score: float, recommendation: str) -> Optional[dict]:
        """Get AI assessment for nuanced analysis."""
        if not self._ai_manager:
            return None

        try:
            prompt = self._build_ai_prompt(alert, strategy, market_data, risk_score, recommendation)
            response = await self._ai_manager.generate(
                messages=[AIMessage(role="user", content=prompt)],
                system_prompt=self._get_system_prompt(),
                max_tokens=256,
                temperature=0.3,
            )
            return self._parse_ai_response(response.content)
        except Exception:
            return None

    def _get_system_prompt(self) -> str:
        return """You are an options profit management specialist. Analyze butterfly position risk.

Respond with ONLY a valid JSON object:
{
  "reasoning": "Brief risk assessment",
  "override_to_exit": boolean (true only if immediate exit is critical)
}

Consider theta decay acceleration, gamma exposure, and potential for profit erosion."""

    def _build_ai_prompt(self, alert: Alert, strategy: dict, market_data: dict,
                          risk_score: float, recommendation: str) -> str:
        spot = market_data.get('spot_price') or market_data.get('spot', 'N/A')
        vix = market_data.get('vix', 'N/A')
        dte = strategy.get('dte', alert.mgmt_initial_dte or 'N/A')
        strike = strategy.get('strike', 'N/A')
        current_profit = (alert.entry_debit or 0) - (strategy.get('current_debit', 0) or 0)
        hwm = alert.mgmt_high_water_mark or 0

        return f"""Butterfly profit management assessment:

Position: Strike {strike}, DTE {dte}
Spot: {spot}
VIX: {vix}

Current Profit: ${current_profit:.2f}
High Water Mark: ${hwm:.2f}
Risk Score: {risk_score:.1f}/100
Initial Recommendation: {recommendation}

Should we override to EXIT? Only if position is at critical risk of losing all profits."""

    def _parse_ai_response(self, content: str) -> Optional[dict]:
        """Parse AI response."""
        try:
            content = content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])
            return json.loads(content)
        except Exception:
            return None


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


class OrderQueueEvaluator:
    """
    Evaluator for the order queue in simulated trading.
    Monitors pending orders against current prices and fills them when conditions are met.
    Also handles order expiration and auto-close of open trades at market close.
    """

    def __init__(self, db=None, logger=None):
        self._db = db
        self._logger = logger

    async def evaluate_orders(self, market_data: dict) -> dict:
        """
        Evaluate all pending orders against current market data.

        Returns dict with:
        - filled_entries: List of orders that were filled (new trades created)
        - filled_exits: List of orders that were filled (trades closed)
        - expired: List of orders that expired
        - auto_closed: List of trades auto-closed at market close
        """
        if not self._db:
            return {'filled_entries': [], 'filled_exits': [], 'expired': [], 'auto_closed': []}

        results = {
            'filled_entries': [],
            'filled_exits': [],
            'expired': [],
            'auto_closed': []
        }

        # First, expire any orders past their expiration time
        expired_count = self._db.expire_orders()
        if expired_count > 0 and self._logger:
            self._logger.info(f"Expired {expired_count} orders", emoji="⏰")

        # Get all pending orders
        pending_orders = self._db.list_pending_orders()

        for order in pending_orders:
            # Get current price for the symbol
            symbol_data = market_data.get(order.symbol, {})
            spot = symbol_data.get('spot_price') or symbol_data.get('spot') or market_data.get('spot_price') or market_data.get('spot')

            if spot is None:
                continue

            # Get bid/ask for realistic execution
            bid = symbol_data.get('bid') or spot * 0.9999
            ask = symbol_data.get('ask') or spot * 1.0001

            filled = False
            fill_price = None

            if order.order_type == 'entry':
                # Entry order fill logic
                if order.direction == 'long':
                    # Long entry: fill at ask when spot reaches limit price
                    if spot <= order.limit_price:
                        filled = True
                        fill_price = ask  # Buy at ask
                else:  # short
                    # Short entry: fill at bid when spot reaches limit price
                    if spot >= order.limit_price:
                        filled = True
                        fill_price = bid  # Sell at bid
            else:  # exit order
                if order.direction == 'long':
                    # Long exit (take profit): fill at bid when spot reaches limit
                    if spot >= order.limit_price:
                        filled = True
                        fill_price = bid  # Sell at bid
                else:  # short
                    # Short exit (take profit): fill at ask when spot reaches limit
                    if spot <= order.limit_price:
                        filled = True
                        fill_price = ask  # Buy at ask

            if filled:
                await self._fill_order(order, fill_price, market_data, results)

        return results

    async def _fill_order(self, order, fill_price: float, market_data: dict, results: dict):
        """Fill an order and create/close the trade.

        When an entry order is filled, the resulting trade becomes immutable (core fields locked).
        This preserves the time-anchored truth of the position for learning and bias detection.
        """
        from datetime import datetime

        if order.order_type == 'entry':
            # Create a new trade from the entry order
            # Note: This would require log_id which isn't stored in order
            # For now, we mark the order as filled and let the UI handle trade creation
            # The UI should call lock_simulated_trade after creating the trade
            self._db.update_order_status(order.id, 'filled', fill_price)
            results['filled_entries'].append({
                'order_id': order.id,
                'symbol': order.symbol,
                'direction': order.direction,
                'limit_price': order.limit_price,
                'fill_price': fill_price,
                'quantity': order.quantity,
                # Flag that this trade should be locked immediately
                'should_lock': True
            })
            if self._logger:
                self._logger.info(
                    f"Filled entry order #{order.id}: {order.direction} {order.symbol} @ ${fill_price:.2f}",
                    emoji="✅"
                )
        else:  # exit order
            # Close the associated trade
            if order.trade_id:
                trade = self._db.get_trade(order.trade_id)
                if trade and trade.status == 'open':
                    # Close the trade at fill price
                    fill_price_cents = int(fill_price * 100)
                    self._db.close_trade(
                        trade_id=order.trade_id,
                        exit_price=fill_price_cents,
                        exit_spot=market_data.get('spot_price') or market_data.get('spot'),
                        exit_time=datetime.utcnow().isoformat()
                    )

            self._db.update_order_status(order.id, 'filled', fill_price)
            results['filled_exits'].append({
                'order_id': order.id,
                'trade_id': order.trade_id,
                'symbol': order.symbol,
                'direction': order.direction,
                'limit_price': order.limit_price,
                'fill_price': fill_price
            })
            if self._logger:
                self._logger.info(
                    f"Filled exit order #{order.id}: closed trade {order.trade_id} @ ${fill_price:.2f}",
                    emoji="✅"
                )

    async def auto_close_at_market_close(self, market_data: dict) -> list:
        """
        Auto-close all open simulated trades at market close (4:00 PM ET).
        Called at market close by the alert engine.

        Returns list of auto-closed trade IDs.
        """
        if not self._db:
            return []

        from datetime import datetime

        auto_closed = []
        spot = market_data.get('spot_price') or market_data.get('spot')

        if spot is None:
            return []

        # Get all open trades with entry_mode='simulated'
        # This requires adding a method to db_v2.py to list simulated open trades
        # For now, we'll handle this via a direct query pattern

        # Mark spot as exit price
        exit_price_cents = int(spot * 100)
        exit_time = datetime.utcnow().isoformat()

        # TODO: Add db method to get open simulated trades and close them
        # For now, return empty - the actual implementation would need
        # a list_open_simulated_trades method in the DB layer

        if self._logger and auto_closed:
            self._logger.info(
                f"Auto-closed {len(auto_closed)} simulated trades at market close",
                emoji="🔔"
            )

        return auto_closed


class PortfolioPnLEvaluator(BaseEvaluator):
    """
    Evaluates portfolio-level aggregate P&L alerts.
    Sums P&L across all strategies and checks against threshold.
    Fast loop, no AI.
    """

    @property
    def alert_type(self) -> str:
        return "portfolio_pnl"

    @property
    def is_ai_powered(self) -> bool:
        return False

    async def evaluate(self, alert: Alert, market_data: dict) -> AlertEvaluation:
        strategies = market_data.get("strategies", {})
        if not strategies:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning="No strategy data available for portfolio P&L",
            )

        total_pnl = 0.0
        for strat_id, strat in strategies.items():
            current_debit = strat.get("current_debit") or strat.get("debit")
            entry_debit = strat.get("entry_debit")
            if current_debit is not None and entry_debit is not None:
                total_pnl += entry_debit - current_debit

        target = alert.target_value
        condition = alert.condition

        condition_met = False
        if condition == "below":
            condition_met = total_pnl < target
        elif condition == "above":
            condition_met = total_pnl > target

        return AlertEvaluation(
            alert_id=alert.id,
            should_trigger=condition_met,
            confidence=1.0 if condition_met else 0.0,
            reasoning=f"Portfolio P&L ${total_pnl:.2f} {'crossed' if condition_met else 'has not crossed'} ${target:.2f} ({condition})",
        )


class PortfolioTrailingEvaluator(BaseEvaluator):
    """
    Evaluates portfolio-level trailing drawdown from session high water mark.
    Tracks aggregate P&L HWM and triggers when drawdown exceeds threshold.
    Fast loop, no AI.
    """

    @property
    def alert_type(self) -> str:
        return "portfolio_trailing"

    @property
    def is_ai_powered(self) -> bool:
        return False

    async def evaluate(self, alert: Alert, market_data: dict) -> AlertEvaluation:
        strategies = market_data.get("strategies", {})
        if not strategies:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning="No strategy data available for portfolio trailing",
            )

        total_pnl = 0.0
        for strat_id, strat in strategies.items():
            current_debit = strat.get("current_debit") or strat.get("debit")
            entry_debit = strat.get("entry_debit")
            if current_debit is not None and entry_debit is not None:
                total_pnl += entry_debit - current_debit

        # Update high water mark
        hwm = alert.high_water_mark or 0
        if total_pnl > hwm:
            alert.high_water_mark = total_pnl
            hwm = total_pnl

        drawdown = hwm - total_pnl if hwm > 0 else 0
        stop_amount = alert.target_value

        condition_met = drawdown >= stop_amount and hwm > 0

        return AlertEvaluation(
            alert_id=alert.id,
            should_trigger=condition_met,
            confidence=1.0 if condition_met else 0.0,
            reasoning=f"Portfolio drawdown ${drawdown:.2f} from HWM ${hwm:.2f} {'exceeded' if condition_met else 'below'} stop ${stop_amount:.2f}",
        )


class GreeksThresholdEvaluator(BaseEvaluator):
    """
    Evaluates aggregate Greeks threshold alerts.
    Checks delta, gamma, or theta against a numeric threshold.
    Fast loop, deterministic, no AI.
    """

    @property
    def alert_type(self) -> str:
        return "greeks_threshold"

    @property
    def is_ai_powered(self) -> bool:
        return False

    async def evaluate(self, alert: Alert, market_data: dict) -> AlertEvaluation:
        greeks = market_data.get("greeks", {})
        if not greeks:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning="No Greeks data available",
            )

        # alert.label stores which Greek to check (delta/gamma/theta)
        greek_name = alert.label or "delta"
        greek_value = greeks.get(greek_name)

        if greek_value is None:
            return AlertEvaluation(
                alert_id=alert.id,
                should_trigger=False,
                confidence=0.0,
                reasoning=f"Greek '{greek_name}' not available in market data",
            )

        target = alert.target_value
        condition = alert.condition

        condition_met = False
        if condition == "above":
            condition_met = greek_value > target
        elif condition == "below":
            condition_met = greek_value < target

        return AlertEvaluation(
            alert_id=alert.id,
            should_trigger=condition_met,
            confidence=1.0 if condition_met else 0.0,
            reasoning=f"{greek_name} {greek_value:.4f} {'crossed' if condition_met else 'has not crossed'} {target} ({condition})",
        )


def create_all_evaluators(ai_manager: Optional[AIProviderManager] = None, logger=None) -> list:
    """
    Factory function to create all evaluators.

    Args:
        ai_manager: AI provider manager for AI-powered evaluators
        logger: Optional logger for evaluators

    Returns:
        List of all evaluator instances
    """
    from .prompt_evaluator import PromptDrivenEvaluator
    from .reference_state_capture import ReferenceStateCaptureService
    from .algo_alert_evaluator import AlgoAlertEvaluator

    reference_service = ReferenceStateCaptureService(logger)

    return [
        PriceEvaluator(),
        DebitEvaluator(),
        ProfitTargetEvaluator(),
        TrailingStopEvaluator(),
        AIThetaGammaEvaluator(ai_manager),
        AISentimentEvaluator(ai_manager),
        AIRiskZoneEvaluator(ai_manager),
        ButterflyEntryEvaluator(),
        ButterflyProfitMgmtEvaluator(ai_manager),
        PromptDrivenEvaluator(ai_manager, reference_service, logger),
        AlgoAlertEvaluator(logger=logger),
        PortfolioPnLEvaluator(),
        PortfolioTrailingEvaluator(),
        GreeksThresholdEvaluator(),
    ]
