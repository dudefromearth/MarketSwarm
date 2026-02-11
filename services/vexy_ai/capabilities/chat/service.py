"""
Chat Service - Business logic for Vexy Chat.

Provides direct conversational access to Vexy with:
- Tier-based access control
- Rate limiting
- Playbook awareness
- Echo Memory integration
- Rich context formatting
"""

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from shared.ai_client import call_ai, AIClientConfig

from .models import ChatContext, UserProfile


class ChatService:
    """
    Vexy Chat service.

    Handles all Chat-related business logic including:
    - Rate limiting
    - Prompt building with tier awareness
    - Context formatting
    - AI calls
    """

    def __init__(self, config: Dict[str, Any], logger: Any, buses: Any = None):
        self.config = config
        self.logger = logger
        self.buses = buses
        # Daily usage tracking (in production, stored in Redis)
        self._usage_cache: Dict[str, int] = {}

    def check_rate_limit(self, user_id: int, tier: str) -> Tuple[bool, int]:
        """
        Check if user can send a message based on rate limits.

        Returns (allowed, remaining).
        """
        from services.vexy_ai.tier_config import get_tier_config

        tier_config = get_tier_config(tier)
        limit = tier_config.daily_limit

        # Unlimited for admins
        if limit == -1:
            return True, -1

        # Try sync Redis for rate limiting
        try:
            from redis import Redis as SyncRedis
            buses = self.config.get("buses", {}) or {}
            system_url = buses.get("system-redis", {}).get("url", "redis://127.0.0.1:6379")
            r = SyncRedis.from_url(system_url, decode_responses=True)
            key = f"vexy_chat:{user_id}:{date.today().isoformat()}"
            current = r.get(key)
            current_count = int(current) if current else 0
            remaining = max(0, limit - current_count)
            return remaining > 0, remaining
        except Exception as e:
            self.logger.warn(f"Redis rate limit check failed: {e}", emoji="⚠️")

        # Fallback to in-memory
        cache_key = f"{user_id}:{date.today().isoformat()}"
        current_count = self._usage_cache.get(cache_key, 0)
        remaining = max(0, limit - current_count)
        return remaining > 0, remaining

    def increment_usage(self, user_id: int) -> None:
        """Increment daily usage counter."""
        # Try sync Redis for rate limiting
        try:
            from redis import Redis as SyncRedis
            buses = self.config.get("buses", {}) or {}
            system_url = buses.get("system-redis", {}).get("url", "redis://127.0.0.1:6379")
            r = SyncRedis.from_url(system_url, decode_responses=True)
            key = f"vexy_chat:{user_id}:{date.today().isoformat()}"
            r.incr(key)
            r.expire(key, 86400 * 2)  # 2 day TTL
            return
        except Exception as e:
            self.logger.warn(f"Redis usage increment failed: {e}", emoji="⚠️")

        # Fallback to in-memory
        cache_key = f"{user_id}:{date.today().isoformat()}"
        self._usage_cache[cache_key] = self._usage_cache.get(cache_key, 0) + 1

    def build_system_prompt(
        self,
        tier: str,
        user_id: int,
        user_message: str = "",
        user_profile: Optional[UserProfile] = None,
    ) -> str:
        """
        Build system prompt for chat based on tier and user profile.

        Includes:
        - Chat outlet base prompt
        - User identity context
        - Tier-specific semantic guardrails
        - Playbook awareness
        - Echo Memory context
        """
        from services.vexy_ai.tier_config import get_tier_config
        # Use dynamic playbook loader (includes file-based playbooks)
        try:
            from services.vexy_ai.playbook_loader import (
                get_playbooks_for_tier_dynamic as get_playbooks_for_tier,
                find_relevant_playbooks_dynamic as find_relevant_playbooks,
            )
        except ImportError:
            from services.vexy_ai.playbook_manifest import (
                get_playbooks_for_tier,
                find_relevant_playbooks,
            )

        tier_config = get_tier_config(tier)

        # Get prompts (check prompt_admin for custom versions)
        try:
            from services.vexy_ai.prompt_admin import get_prompt, get_tier_prompt
            chat_prompt = get_prompt("chat")
            tier_prompt = get_tier_prompt(tier)
        except ImportError:
            from services.vexy_ai.outlet_prompts import get_outlet_prompt
            chat_prompt = get_outlet_prompt("chat")
            tier_prompt = tier_config.system_prompt_suffix

        prompt_parts = [chat_prompt]

        # Add user identity context
        if user_profile and user_profile.display_name:
            prompt_parts.append("\n\n---\n")
            prompt_parts.append(f"## User Identity\n")
            prompt_parts.append(f"You are speaking with **{user_profile.display_name}**.\n")
            if user_profile.is_admin:
                prompt_parts.append("They have admin access to the system.\n")
            prompt_parts.append("Use their name naturally in conversation when appropriate.\n")

        # Add tier-specific semantic scope
        prompt_parts.append("\n\n---\n")
        prompt_parts.append(tier_prompt)

        # Add Playbook awareness
        accessible_playbooks = get_playbooks_for_tier(tier)
        if accessible_playbooks:
            relevant = find_relevant_playbooks(user_message, tier, max_results=3) if user_message else []

            prompt_parts.append("\n\n---\n")

            if relevant:
                prompt_parts.append("## Relevant Playbooks for This Query\n")
                for pb in relevant:
                    prompt_parts.append(f"- **{pb.name}** ({pb.scope}): {pb.description}\n")
                prompt_parts.append("\n")

            prompt_parts.append("## All Accessible Playbooks\n")
            for pb in accessible_playbooks:
                prompt_parts.append(f"- {pb.name} ({pb.scope})\n")

            prompt_parts.append("\n")
            prompt_parts.append("**Instruction:** When relevant, reference these Playbooks by name rather than explaining their content inline. ")
            prompt_parts.append("Playbooks hold structure; you hold presence. Prefer redirection to inline explanation.\n")

        # Add Echo Memory if enabled
        if tier_config.echo_enabled:
            try:
                from services.vexy_ai.intel.echo_memory import get_echo_context_for_prompt
                echo_context = get_echo_context_for_prompt(user_id, days=tier_config.echo_days)
                if echo_context and "No prior Echo" not in echo_context:
                    prompt_parts.append("\n\n---\n")
                    prompt_parts.append(echo_context)
            except Exception as e:
                self.logger.warn(f"Echo context unavailable: {e}", emoji="🔇")

        return "".join(prompt_parts)

    def format_context(self, context: Optional[ChatContext]) -> str:
        """Format comprehensive chat context for the prompt."""
        if not context:
            return ""

        parts = []

        # Market data
        if context.market_data:
            md = context.market_data
            market_parts = []

            # Handle both naming conventions (frontend uses spxPrice, backend may use spx)
            spx = md.get("spxPrice") or md.get("spx")
            vix = md.get("vixLevel") or md.get("vix")
            vix_regime = md.get("vixRegime")
            market_mode = md.get("marketMode") or md.get("market_mode")
            ds = md.get("directionalStrength") or md.get("directional_strength")

            if spx:
                spx_change = md.get("spxChangePercent") or md.get("spx_change_percent")
                if spx_change:
                    market_parts.append(f"SPX: {spx:.2f} ({spx_change:+.2f}%)")
                else:
                    market_parts.append(f"SPX: {spx:.2f}")
            if vix:
                if vix_regime:
                    market_parts.append(f"VIX: {vix:.1f} ({vix_regime})")
                else:
                    market_parts.append(f"VIX: {vix:.1f}")
            if market_mode:
                market_parts.append(f"Mode: {market_mode}")
            if ds is not None:
                bias = "bullish" if ds > 0.3 else "bearish" if ds < -0.3 else "neutral"
                market_parts.append(f"Bias: {bias}")

            if market_parts:
                parts.append("## Market Context\n" + ", ".join(market_parts))

        # Positions (Trade Log data)
        if context.positions:
            pos_summary = []
            for pos in context.positions[:5]:  # Limit to 5
                # Handle frontend format (type, strikes, pnl) and backend format (strategy, status, pnl)
                pos_type = pos.get("type") or pos.get("strategy") or "Position"
                symbol = pos.get("symbol", "SPX")
                direction = pos.get("direction", "")
                strikes = pos.get("strikes", [])
                expiration = pos.get("expiration", "")
                pnl = pos.get("pnl")
                pnl_pct = pos.get("pnlPercent") or pos.get("pnl_percent")
                days_to_exp = pos.get("daysToExpiry") or pos.get("days_to_expiry")

                # Build position line
                pos_line = f"- {pos_type}"
                if direction:
                    pos_line += f" ({direction})"
                if strikes:
                    pos_line += f" @ {'/'.join(str(s) for s in strikes[:3])}"
                if days_to_exp is not None:
                    pos_line += f" [{days_to_exp}d]"
                if pnl is not None:
                    pos_line += f": ${pnl:+.0f}"
                    if pnl_pct is not None:
                        pos_line += f" ({pnl_pct:+.1f}%)"

                pos_summary.append(pos_line)

            if pos_summary:
                parts.append("## Open Positions (Trade Log)\n" + "\n".join(pos_summary))

        # Trading activity
        if context.trading:
            tr = context.trading
            trading_parts = []

            # Handle both naming conventions
            today_trades = tr.get("todayTrades") or tr.get("trades_today") or 0
            open_trades = tr.get("openTrades") or tr.get("open_trades") or 0
            closed_trades = tr.get("closedTrades") or tr.get("closed_trades") or 0
            win_rate = tr.get("winRate") or tr.get("win_rate")
            today_pnl = tr.get("todayPnl") or tr.get("pnl_today")
            week_pnl = tr.get("weekPnl") or tr.get("week_pnl")

            if open_trades:
                trading_parts.append(f"Open: {open_trades}")
            if closed_trades:
                trading_parts.append(f"Closed: {closed_trades}")
            if today_trades:
                trading_parts.append(f"Today: {today_trades}")
            if win_rate is not None:
                # Handle both decimal (0.65) and percentage (65) formats
                if win_rate <= 1:
                    trading_parts.append(f"Win rate: {win_rate:.0%}")
                else:
                    trading_parts.append(f"Win rate: {win_rate:.0f}%")
            if today_pnl is not None:
                trading_parts.append(f"Today P&L: ${today_pnl:+.0f}")
            if week_pnl is not None:
                trading_parts.append(f"Week P&L: ${week_pnl:+.0f}")

            if trading_parts:
                parts.append("## Trading Activity\n" + ", ".join(trading_parts))

        # Risk Graph
        if context.risk:
            risk = context.risk
            risk_parts = []

            strategies = risk.get("strategiesOnGraph") or risk.get("strategies_on_graph") or 0
            max_profit = risk.get("totalMaxProfit") or risk.get("max_profit")
            max_loss = risk.get("totalMaxLoss") or risk.get("max_loss")
            breakevens = risk.get("breakevenPoints") or risk.get("breakeven_points") or []

            if strategies:
                risk_parts.append(f"Strategies displayed: {strategies}")
            if max_profit is not None:
                risk_parts.append(f"Max profit: ${max_profit:+.0f}")
            if max_loss is not None:
                risk_parts.append(f"Max loss: ${max_loss:.0f}")
            if breakevens:
                risk_parts.append(f"Breakevens: {', '.join(str(b) for b in breakevens[:3])}")

            if risk_parts:
                parts.append("## Risk Graph\n" + ", ".join(risk_parts))

        # Alerts
        if context.alerts:
            alerts = context.alerts
            alert_parts = []

            armed = alerts.get("armed") or 0
            triggered = alerts.get("triggered") or 0
            recent = alerts.get("recentTriggers") or alerts.get("recent_triggers") or []

            if armed:
                alert_parts.append(f"Armed: {armed}")
            if triggered:
                alert_parts.append(f"Triggered: {triggered}")

            if alert_parts:
                alert_text = "## Alerts\n" + ", ".join(alert_parts)
                if recent:
                    alert_text += "\nRecent: " + "; ".join(
                        f"{r.get('type', 'alert')}: {r.get('message', '')}"
                        for r in recent[:3]
                    )
                parts.append(alert_text)

        # UI state
        if context.ui:
            ui = context.ui
            ui_parts = []

            panel = ui.get("activePanel") or ui.get("current_panel")
            stage = ui.get("currentStage") or ui.get("current_stage")

            if panel:
                ui_parts.append(f"Active panel: {panel}")
            if stage:
                ui_parts.append(f"Stage: {stage}")

            if ui_parts:
                parts.append("## UI State\n" + ", ".join(ui_parts))

        return "\n\n".join(parts) if parts else ""

    async def chat(
        self,
        message: str,
        user_id: int,
        user_tier: str,
        reflection_dial: float,
        context: Optional[ChatContext] = None,
        user_profile: Optional[UserProfile] = None,
    ) -> Dict[str, Any]:
        """
        Handle a Vexy chat message.

        Returns response with tokens used and remaining quota.
        """
        from services.vexy_ai.tier_config import get_tier_config, validate_reflection_dial

        tier_config = get_tier_config(user_tier)

        # Validate reflection dial
        reflection_dial = validate_reflection_dial(user_tier, reflection_dial)

        # Build system prompt with user profile
        system_prompt = self.build_system_prompt(user_tier, user_id, message, user_profile)

        # Build user prompt with context
        user_prompt_parts = []

        # Add context
        context_text = self.format_context(context)
        if context_text:
            user_prompt_parts.append(context_text)
            user_prompt_parts.append("\n---\n")

        # Add reflection dial guidance
        if reflection_dial <= 0.4:
            user_prompt_parts.append("(Reflection dial: Low. Keep response brief and observational.)\n\n")
        elif reflection_dial >= 0.7:
            user_prompt_parts.append("(Reflection dial: High. Probe deeper, challenge gently.)\n\n")

        user_prompt_parts.append(message)
        user_prompt = "".join(user_prompt_parts)

        # Call AI
        ai_response = await call_ai(
            system_prompt=system_prompt,
            user_message=user_prompt,
            config=self.config,
            ai_config=AIClientConfig(
                timeout=90.0,
                temperature=0.7,
                max_tokens=600,
                enable_web_search=True,
            ),
            logger=self.logger,
        )

        # AIResponse is a dataclass, access attributes directly
        response_text = ai_response.text
        tokens_used = ai_response.tokens_used

        # Increment usage
        self.increment_usage(user_id)

        # Get remaining quota
        _, remaining = self.check_rate_limit(user_id, user_tier)

        self.logger.info(f"Chat response for user {user_id}: {len(response_text)} chars", emoji="🦋")

        return {
            "response": response_text.strip(),
            "agent": None,  # TODO: Detect agent from response
            "echo_updated": False,  # TODO: Implement echo update
            "tokens_used": tokens_used,
            "remaining_today": remaining if remaining >= 0 else -1,
        }
