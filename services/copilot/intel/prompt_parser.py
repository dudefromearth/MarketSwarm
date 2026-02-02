# services/copilot/intel/prompt_parser.py
"""
PromptParserService - AI-powered natural language prompt parsing.

Parses trader prompts into 4 semantic zones:
1. Reference State - what baseline to capture
2. Deviation Logic - what changes to watch
3. Evaluation Mode - when to check (regular/threshold/event)
4. Stage Thresholds - what constitutes update/warn/accomplished
"""

import json
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any

from .ai_providers import AIProviderManager, AIMessage


@dataclass
class ParsedPrompt:
    """Result of parsing a natural language prompt."""
    reference_logic: Dict[str, Any]
    deviation_logic: Dict[str, Any]
    evaluation_mode: str  # regular, threshold, event
    stage_thresholds: Dict[str, Any]
    confidence: float
    parsing_notes: Optional[str] = None


class PromptParserService:
    """
    Parses natural language prompts into structured semantic zones.

    Uses AI to extract meaningful conditions from trader descriptions like:
    "Alert me if gamma starts eating into my profit zone as we get closer to
    expiration. I want to protect at least 40% of the max profit."
    """

    def __init__(self, ai_manager: Optional[AIProviderManager] = None, logger=None):
        self._ai_manager = ai_manager
        self._logger = logger

    def _log(self, msg: str, level: str = "info"):
        if self._logger:
            fn = getattr(self._logger, level, self._logger.info)
            fn(msg)

    async def parse_prompt(
        self,
        prompt: str,
        strategy_context: Dict[str, Any]
    ) -> ParsedPrompt:
        """
        Parse a natural language prompt into semantic zones.

        Args:
            prompt: Natural language alert description from trader
            strategy_context: Current strategy state (Greeks, P&L, DTE, etc.)

        Returns:
            ParsedPrompt with extracted semantic zones
        """
        if not self._ai_manager:
            return self._fallback_parse(prompt, strategy_context)

        system_prompt = self._get_system_prompt()
        user_prompt = self._build_user_prompt(prompt, strategy_context)

        try:
            start_time = time.time()
            response = await self._ai_manager.generate(
                messages=[AIMessage(role="user", content=user_prompt)],
                system_prompt=system_prompt,
                max_tokens=1024,
                temperature=0.2,
            )
            latency_ms = (time.time() - start_time) * 1000

            self._log(f"Prompt parsing completed in {latency_ms:.0f}ms")

            return self._parse_ai_response(response.content, prompt)

        except Exception as e:
            self._log(f"AI prompt parsing failed: {e}", level="warn")
            return self._fallback_parse(prompt, strategy_context)

    def _get_system_prompt(self) -> str:
        return """You are an expert at understanding trader intent. Parse natural language trading alerts into structured conditions.

You must respond with ONLY a valid JSON object (no markdown, no explanation outside JSON):
{
    "reference_logic": {
        "metrics": ["gamma", "theta", "delta", "max_profit", "pnl", "breakevens", "dte"],
        "capture_fields": ["specific fields from strategy to baseline"],
        "notes": "what the trader considers the 'starting point'"
    },
    "deviation_logic": {
        "watch_for": "what change triggers attention",
        "direction": "increase|decrease|either|threshold",
        "metric": "primary metric being watched",
        "comparison_type": "percentage|absolute|ratio",
        "comparison_target": "what to compare against",
        "notes": "detailed interpretation of the deviation"
    },
    "evaluation_mode": "regular|threshold|event",
    "stage_thresholds": {
        "update_trigger": {
            "condition": "when to move to 'update' stage",
            "threshold_percentage": 0.25
        },
        "warn_trigger": {
            "condition": "when to move to 'warn' stage",
            "threshold_percentage": 0.50
        },
        "accomplished_trigger": {
            "condition": "when alert objective is accomplished",
            "outcome": "protection applied or objective met"
        }
    },
    "confidence": 0.85,
    "parsing_notes": "any ambiguities or assumptions made"
}

Evaluation modes:
- "regular": Check on every evaluation cycle (most common)
- "threshold": Only evaluate when a specific metric crosses a level
- "event": Only evaluate on specific events (e.g., trade close, DTE change)

Stage flow: watching -> update -> warn -> accomplished
- watching: passively monitoring
- update: change detected, informational
- warn: approaching critical threshold
- accomplished: objective met (protection triggered, target reached, etc.)

Example prompt: "Alert me if gamma starts eating into my profit zone as we get closer to expiration. I want to protect at least 40% of the max profit."

Would yield:
- reference_logic: Capture gamma, current profit as % of max
- deviation_logic: Watch for gamma increasing AND profit percentage decreasing
- evaluation_mode: regular
- stage_thresholds: update at 60% profit remaining, warn at 45% profit remaining, accomplished when protection applied or position closed"""

    def _build_user_prompt(self, prompt: str, strategy_context: Dict[str, Any]) -> str:
        """Build the user prompt with context."""
        ctx_str = json.dumps(strategy_context, indent=2, default=str)

        return f"""Parse this trader's alert prompt into structured semantic zones.

TRADER'S PROMPT:
"{prompt}"

CURRENT STRATEGY CONTEXT:
{ctx_str}

Extract the reference state, deviation logic, evaluation mode, and stage thresholds from the prompt.
Consider the strategy context to understand what metrics are available and relevant."""

    def _parse_ai_response(self, content: str, original_prompt: str) -> ParsedPrompt:
        """Parse AI response into ParsedPrompt."""
        try:
            content = content.strip()

            # Handle markdown code blocks
            if content.startswith("```"):
                lines = content.split("\n")
                # Find the end of code block
                end_idx = len(lines) - 1
                for i in range(1, len(lines)):
                    if lines[i].startswith("```"):
                        end_idx = i
                        break
                content = "\n".join(lines[1:end_idx])

            data = json.loads(content)

            return ParsedPrompt(
                reference_logic=data.get("reference_logic", {}),
                deviation_logic=data.get("deviation_logic", {}),
                evaluation_mode=data.get("evaluation_mode", "regular"),
                stage_thresholds=data.get("stage_thresholds", {}),
                confidence=float(data.get("confidence", 0.5)),
                parsing_notes=data.get("parsing_notes"),
            )

        except (json.JSONDecodeError, KeyError) as e:
            self._log(f"Failed to parse AI response: {e}", level="warn")
            return self._fallback_parse(original_prompt, {})

    def _fallback_parse(self, prompt: str, strategy_context: Dict[str, Any]) -> ParsedPrompt:
        """Fallback parsing when AI is unavailable or fails."""
        prompt_lower = prompt.lower()

        # Detect metrics mentioned
        metrics = []
        if "gamma" in prompt_lower:
            metrics.append("gamma")
        if "theta" in prompt_lower:
            metrics.append("theta")
        if "delta" in prompt_lower:
            metrics.append("delta")
        if "profit" in prompt_lower:
            metrics.append("pnl")
        if "breakeven" in prompt_lower:
            metrics.append("breakevens")
        if not metrics:
            metrics = ["pnl", "gamma"]  # Default to P&L and gamma

        # Detect thresholds mentioned
        threshold_pct = 0.5  # Default 50%
        import re
        pct_match = re.search(r'(\d+)\s*%', prompt)
        if pct_match:
            threshold_pct = int(pct_match.group(1)) / 100

        # Detect evaluation mode
        evaluation_mode = "regular"
        if "when" in prompt_lower and ("crosses" in prompt_lower or "reaches" in prompt_lower):
            evaluation_mode = "threshold"
        elif "on" in prompt_lower and ("close" in prompt_lower or "event" in prompt_lower):
            evaluation_mode = "event"

        return ParsedPrompt(
            reference_logic={
                "metrics": metrics,
                "capture_fields": metrics,
                "notes": "Fallback parsing - captured mentioned metrics"
            },
            deviation_logic={
                "watch_for": "change in primary metric",
                "direction": "either",
                "metric": metrics[0] if metrics else "pnl",
                "comparison_type": "percentage",
                "comparison_target": "reference",
                "notes": "Fallback parsing - basic deviation detection"
            },
            evaluation_mode=evaluation_mode,
            stage_thresholds={
                "update_trigger": {
                    "condition": f"Change detected in {metrics[0] if metrics else 'primary metric'}",
                    "threshold_percentage": threshold_pct * 0.5
                },
                "warn_trigger": {
                    "condition": f"Approaching threshold of {threshold_pct*100:.0f}%",
                    "threshold_percentage": threshold_pct * 0.75
                },
                "accomplished_trigger": {
                    "condition": f"Threshold of {threshold_pct*100:.0f}% reached",
                    "outcome": "protection triggered"
                }
            },
            confidence=0.3,
            parsing_notes="Fallback parsing used - AI unavailable or failed"
        )

    def serialize_parsed_prompt(self, parsed: ParsedPrompt) -> Dict[str, str]:
        """Serialize ParsedPrompt to JSON strings for database storage."""
        return {
            "parsed_reference_logic": json.dumps(parsed.reference_logic),
            "parsed_deviation_logic": json.dumps(parsed.deviation_logic),
            "parsed_evaluation_mode": parsed.evaluation_mode,
            "parsed_stage_thresholds": json.dumps(parsed.stage_thresholds),
        }
