"""
Chat Service - Business logic for Vexy Chat.

Provides direct conversational access to Vexy with:
- Tier-based access control
- Rate limiting
- Rich context formatting
- All LLM calls route through VexyKernel
"""

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from .models import ChatContext, UserProfile


class ChatService:
    """
    Vexy Chat service.

    Handles all Chat-related business logic including:
    - Rate limiting
    - Context formatting
    - Kernel-routed AI calls (via VexyKernel.reason())

    What moved to kernel: System prompt assembly, ORA validation,
    forbidden language checking, despair detection, agent selection.
    What stays here: Rate limiting, usage tracking, format_context().
    """

    def __init__(self, config: Dict[str, Any], logger: Any, buses: Any = None, market_intel=None, kernel=None):
        self.config = config
        self.logger = logger
        self.buses = buses
        self.market_intel = market_intel
        self.kernel = kernel
        # Hourly usage tracking (in production, stored in Redis)
        self._usage_cache: Dict[str, int] = {}

    def check_rate_limit(self, user_id: int, tier: str) -> Tuple[bool, int]:
        """
        Check if user can send a message based on hourly rate limits.

        Returns (allowed, remaining).
        """
        from services.vexy_ai.tier_config import get_tier_config, get_gate_value

        tier_config = get_tier_config(tier)
        limit = tier_config.rate_limit

        # Check dynamic gate override first
        gate_limit = get_gate_value(tier, "vexy_chat_rate")
        if gate_limit is not None:
            limit = int(gate_limit)

        # Unlimited for admins
        if limit == -1:
            return True, -1

        # Try sync Redis for rate limiting
        try:
            from redis import Redis as SyncRedis
            buses = self.config.get("buses", {}) or {}
            system_url = buses.get("system-redis", {}).get("url", "redis://127.0.0.1:6379")
            r = SyncRedis.from_url(system_url, decode_responses=True)
            key = f"vexy_chat:rate:{user_id}"
            current = r.get(key)
            current_count = int(current) if current else 0
            remaining = max(0, limit - current_count)
            return remaining > 0, remaining
        except Exception as e:
            self.logger.warn(f"Redis rate limit check failed: {e}", emoji="⚠️")

        # Fallback to in-memory
        cache_key = f"rate:{user_id}"
        current_count = self._usage_cache.get(cache_key, 0)
        remaining = max(0, limit - current_count)
        return remaining > 0, remaining

    def increment_usage(self, user_id: int) -> None:
        """Increment hourly usage counter."""
        # Try sync Redis for rate limiting
        try:
            from redis import Redis as SyncRedis
            buses = self.config.get("buses", {}) or {}
            system_url = buses.get("system-redis", {}).get("url", "redis://127.0.0.1:6379")
            r = SyncRedis.from_url(system_url, decode_responses=True)
            key = f"vexy_chat:rate:{user_id}"
            r.incr(key)
            r.expire(key, 3600)  # 1 hour sliding window
            return
        except Exception as e:
            self.logger.warn(f"Redis usage increment failed: {e}", emoji="⚠️")

        # Fallback to in-memory
        cache_key = f"rate:{user_id}"
        self._usage_cache[cache_key] = self._usage_cache.get(cache_key, 0) + 1

    # build_system_prompt() removed — now handled by VexyKernel._assemble_system_prompt()

    def _get_som_context(self) -> str:
        """Format current SoM lenses into markdown for chat prompt enrichment."""
        if not self.market_intel:
            return ""
        try:
            som = self.market_intel.get_som()
            if not som:
                return ""

            bpv = som.get("big_picture_volatility")
            lv = som.get("localized_volatility")
            ee = som.get("event_energy")
            ct = som.get("convexity_temperature")

            # Weekend/holiday: all lenses null
            if not bpv and not ct:
                return ""

            lines = ["## Market Intelligence (SoM)"]

            if bpv:
                vix = bpv.get("vix", "?")
                regime = bpv.get("regime_label", "?")
                decay = bpv.get("decay_profile", "?")
                gamma = bpv.get("gamma_sensitivity", "?")
                lines.append(f"VIX: {vix} | Regime: {regime} | Decay: {decay} | Gamma: {gamma}")

            if lv:
                dealer = lv.get("dealer_posture", "?")
                expansion = lv.get("intraday_expansion_probability", "?")
                lines.append(f"Dealer: {dealer} | Expansion: {expansion}")

            if ee:
                events = ee.get("events", [])
                posture = ee.get("event_posture", "clean_morning")
                event_names = ", ".join(e.get("name", "?") for e in events) if events else "None"
                lines.append(f"Events: {event_names} | Posture: {posture}")

            if ct:
                temp = ct.get("temperature", "?")
                summary = ct.get("summary", "")
                lines.append(f"Temperature: {temp} — {summary}")

            return "\n".join(lines)
        except Exception as e:
            self.logger.debug(f"SoM context unavailable for chat: {e}")
            return ""

    def format_context(self, context: Optional[ChatContext]) -> str:
        """Format comprehensive chat context for the prompt."""
        if not context:
            # Even without client context, append SoM if available
            som_context = self._get_som_context()
            return som_context

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

        # Append server-side SoM lenses (regime, temperature, posture)
        som_context = self._get_som_context()
        if som_context:
            parts.append(som_context)

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

        All LLM calls route through VexyKernel.reason().
        Returns response with tokens used and remaining quota.
        """
        from services.vexy_ai.tier_config import validate_reflection_dial

        # Validate reflection dial
        reflection_dial = validate_reflection_dial(user_tier, reflection_dial)

        # Format context (stays in ChatService — domain-specific formatting)
        context_text = self.format_context(context)

        # Build kernel request
        from services.vexy_ai.kernel import ReasoningRequest

        # Prepend formatted context to user message (kernel assembles system prompt)
        user_message_parts = []
        if context_text:
            user_message_parts.append(context_text)
            user_message_parts.append("\n---\n")
        user_message_parts.append(message)
        full_user_message = "".join(user_message_parts)

        request = ReasoningRequest(
            outlet="chat",
            user_message=full_user_message,
            user_id=user_id,
            tier=user_tier,
            reflection_dial=reflection_dial,
            enable_web_search=True,
            user_profile=user_profile,
        )

        # Route through kernel
        response = await self.kernel.reason(request)

        # Increment usage
        self.increment_usage(user_id)

        # Get remaining quota
        _, remaining = self.check_rate_limit(user_id, user_tier)

        self.logger.info(f"Chat response for user {user_id}: {len(response.text)} chars", emoji="🦋")

        return {
            "response": response.text,
            "agent": response.agent_selected,
            "echo_updated": response.echo_updated,
            "tokens_used": response.tokens_used,
            "remaining_today": remaining if remaining >= 0 else -1,
        }
