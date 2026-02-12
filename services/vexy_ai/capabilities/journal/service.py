"""
Journal Service - Business logic for Journal Mode.

Core Doctrine:
- The Journal is not a place to perform work. It is a place to notice what occurred.
- Vexy is silent by default. Presence is assumed. Speech is earned.
- Silence is not a failure state. Silence is correct.

All LLM calls route through VexyKernel.reason().
"""

from datetime import datetime, date
from typing import Any, Dict, List, Optional


class JournalService:
    """
    Journal Mode service.

    Handles all Journal-related business logic including:
    - Daily Synopsis generation (non-LLM)
    - Reflective prompt generation (non-LLM)
    - Journal chat (Mode A and Mode B) — via VexyKernel

    What moved to kernel: System prompt, call_ai, response validation.
    What stays here: generate_synopsis(), generate_prompts(), trade data formatting.
    """

    def __init__(self, config: Dict[str, Any], logger: Any, kernel=None):
        self.config = config
        self.logger = logger
        self.kernel = kernel

    def generate_synopsis(
        self,
        trade_date: str,
        trades: List[Dict[str, Any]],
        market_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate the Daily Synopsis for the Journal.

        The Synopsis is a weather report, not a scorecard.
        """
        from services.vexy_ai.journal_prompts import (
            build_daily_synopsis,
            format_synopsis_text,
        )

        try:
            parsed_date = datetime.fromisoformat(trade_date).date()
        except ValueError:
            parsed_date = date.today()

        synopsis = build_daily_synopsis(
            trade_date=parsed_date,
            trades=trades,
            market_context=market_context,
        )

        return {
            "synopsis_text": format_synopsis_text(synopsis),
            "activity": synopsis.activity,
            "rhythm": synopsis.rhythm,
            "risk_exposure": synopsis.risk_exposure,
            "context": synopsis.context,
        }

    def generate_prompts(
        self,
        trade_date: str,
        trades: List[Dict[str, Any]],
        market_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate prepared reflective prompts for the Journal.

        Rules:
        - Maximum 2 prompts per day, often 0
        - Only if sufficient data exists
        - Silence is preferable to filler
        """
        from services.vexy_ai.journal_prompts import (
            build_daily_synopsis,
            generate_reflective_prompts,
            should_vexy_speak,
        )

        try:
            parsed_date = datetime.fromisoformat(trade_date).date()
        except ValueError:
            parsed_date = date.today()

        synopsis = build_daily_synopsis(
            trade_date=parsed_date,
            trades=trades,
            market_context=market_context,
        )

        # Generate prepared prompts
        prompts = generate_reflective_prompts(synopsis, trades)
        prompt_dicts = [
            {
                "text": p.text,
                "category": p.category.value,
                "grounded_in": p.grounded_in or "",
            }
            for p in prompts
        ]

        # Check if Vexy should speak unprompted
        speak, reflection = should_vexy_speak(synopsis, trades)

        return {
            "prompts": prompt_dicts,
            "should_vexy_speak": speak,
            "vexy_reflection": reflection,
        }

    async def chat(
        self,
        message: str,
        trade_date: str,
        trades: List[Dict[str, Any]],
        market_context: Optional[str] = None,
        is_prepared_prompt: bool = False,
    ) -> Dict[str, Any]:
        """
        Handle Vexy chat in Journal context.

        All LLM calls route through VexyKernel.reason().

        Supports two modes:
        - Mode A: On-Demand Conversation (user asks directly)
        - Mode B: Responding to Prepared Prompts (user clicks a prompt)
        """
        from services.vexy_ai.journal_prompts import (
            build_daily_synopsis,
            format_synopsis_text,
        )

        try:
            parsed_date = datetime.fromisoformat(trade_date).date()
        except ValueError:
            parsed_date = date.today()

        synopsis = build_daily_synopsis(
            trade_date=parsed_date,
            trades=trades,
            market_context=market_context,
        )

        # Build context string with synopsis and trade data
        mode = "prepared" if is_prepared_prompt else "direct"
        context_parts = [
            f"## Journal Context ({mode} mode)\n",
            f"Date: {parsed_date.isoformat()}\n",
        ]

        synopsis_text = format_synopsis_text(synopsis)
        if synopsis_text:
            context_parts.append(f"\n## Daily Synopsis\n{synopsis_text}\n")

        if trades:
            context_parts.append(f"\nTrades today: {len(trades)}\n")
            for t in trades[:5]:
                strategy = t.get("strategy", t.get("type", "trade"))
                pnl = t.get("pnl", t.get("realized_pnl"))
                context_parts.append(f"- {strategy}")
                if pnl is not None:
                    context_parts.append(f": ${pnl:+.0f}")
                context_parts.append("\n")

        context_text = "".join(context_parts)

        # Route through kernel
        from services.vexy_ai.kernel import ReasoningRequest

        # Default user_id to 1 (journal doesn't currently pass user_id)
        request = ReasoningRequest(
            outlet="journal",
            user_message=f"{context_text}\n---\n{message}",
            user_id=1,  # TODO: pass user_id from capability
            tier="navigator",  # TODO: pass tier from capability
            reflection_dial=0.5,
            trades=trades,
        )

        response = await self.kernel.reason(request)

        self.logger.info(f"Journal chat response: {len(response.text)} chars", emoji="📓")

        return {
            "response": response.text,
            "mode": mode,
        }

    # validate_response() removed — now handled by VexyKernel post-LLM validation
