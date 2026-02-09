"""
Journal Service - Business logic for Journal Mode.

Core Doctrine:
- The Journal is not a place to perform work. It is a place to notice what occurred.
- Vexy is silent by default. Presence is assumed. Speech is earned.
- Silence is not a failure state. Silence is correct.
"""

from datetime import datetime, date
from typing import Any, Dict, List, Optional

from shared.ai_client import call_ai, AIClientConfig


class JournalService:
    """
    Journal Mode service.

    Handles all Journal-related business logic including:
    - Daily Synopsis generation
    - Reflective prompt generation
    - Journal chat (Mode A and Mode B)
    """

    def __init__(self, config: Dict[str, Any], logger: Any):
        self.config = config
        self.logger = logger

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

        Supports two modes:
        - Mode A: On-Demand Conversation (user asks directly)
        - Mode B: Responding to Prepared Prompts (user clicks a prompt)
        """
        from services.vexy_ai.journal_prompts import (
            build_daily_synopsis,
            get_journal_prompt,
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

        # Build Journal-specific system prompt
        mode = "prepared" if is_prepared_prompt else "direct"
        system_prompt = get_journal_prompt(
            synopsis=synopsis,
            trades=trades,
            mode=mode,
            prepared_prompt_text=message if is_prepared_prompt else None,
        )

        # Call AI with lower temperature for Journal's neutral tone
        ai_response = await call_ai(
            system_prompt=system_prompt,
            user_message=message,
            config=self.config,
            ai_config=AIClientConfig(
                timeout=60.0,
                temperature=0.6,
                max_tokens=400,
                enable_web_search=False,
            ),
        )

        response_text = ai_response.get("text", "")

        self.logger.info(f"Journal chat response: {len(response_text)} chars", emoji="📓")

        return {
            "response": response_text,
            "mode": mode,
        }

    def validate_response(self, response: str) -> List[str]:
        """Validate response for forbidden language."""
        from services.vexy_ai.journal_prompts import validate_response_language
        return validate_response_language(response)
