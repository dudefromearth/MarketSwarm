#!/usr/bin/env python3

import asyncio
import os
import sys
from pathlib import Path

# ------------------------------------------------------------
# 1) Ensure MarketSwarm root is on sys.path
# ------------------------------------------------------------
# When running as: python services/vexy_ai/main.py
# Python sets sys.path[0] = services/vexy_ai/
# So "shared.*" cannot be resolved unless we add the root.
ROOT = Path(__file__).resolve().parents[2]   # MarketSwarm/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ------------------------------------------------------------
# 2) Imports
# ------------------------------------------------------------
from shared.logutil import LogUtil
from shared.heartbeat import start_heartbeat
from shared.setup_base import SetupBase

# Vexy-specific modules
from services.vexy_ai.intel.orchestrator import run as orchestrator_run
from services.vexy_ai.intel.routine_briefing import RoutineBriefingSynthesizer
from services.vexy_ai.intel.log_health_analyzer import (
    store_routine_context,
    get_routine_context,
    get_log_health_signals_for_briefing,
)
from services.vexy_ai.intel.process_echo import (
    ProcessEchoGenerator,
    format_echoes_for_narrative,
)
from services.vexy_ai.tier_config import (
    get_tier_config,
    validate_reflection_dial,
    tier_from_roles,
)
from services.vexy_ai.intel.echo_memory import get_echo_context_for_prompt
from services.vexy_ai.playbook_manifest import (
    get_playbooks_for_tier,
    find_relevant_playbooks,
    format_playbooks_for_prompt,
)

# FastAPI for HTTP endpoints
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import date, datetime
import uvicorn
import redis
import httpx


SERVICE_NAME = "vexy_ai"
HTTP_PORT = int(os.getenv("VEXY_HTTP_PORT", "3005"))


# ------------------------------------------------------------
# FastAPI Application
# ------------------------------------------------------------
app = FastAPI(title="Vexy AI", version="1.0.0")

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state (set during startup)
_config: Dict[str, Any] = {}
_logger = None
_routine_synthesizer: Optional[RoutineBriefingSynthesizer] = None
_process_echo_generator: Optional[ProcessEchoGenerator] = None
_redis_client: Optional[redis.Redis] = None


# ------------------------------------------------------------
# Pydantic Models for Request/Response
# ------------------------------------------------------------
class MarketContext(BaseModel):
    globex_summary: Optional[str] = None
    vix_level: Optional[float] = None
    vix_regime: Optional[str] = None
    gex_posture: Optional[str] = None
    market_mode: Optional[str] = None
    market_mode_score: Optional[float] = None
    directional_strength: Optional[float] = None
    lfi_score: Optional[float] = None
    spx_value: Optional[float] = None
    spx_change_percent: Optional[float] = None
    opex_proximity: Optional[int] = None
    macro_events_today: Optional[List[Dict[str, Any]]] = None


class UserContext(BaseModel):
    focus: Optional[str] = None
    energy: Optional[str] = None
    emotional_load: Optional[str] = None
    intent: Optional[str] = None
    intent_note: Optional[str] = None
    free_text: Optional[str] = None


class OpenLoops(BaseModel):
    open_trades: int = 0
    unjournaled_closes: int = 0
    armed_alerts: int = 0


class RoutineBriefingRequest(BaseModel):
    mode: str = "routine"
    timestamp: Optional[str] = None
    market_context: Optional[MarketContext] = None
    user_context: Optional[UserContext] = None
    open_loops: Optional[OpenLoops] = None
    user_id: Optional[int] = None  # For fetching log health context


# Log Health Context Models
class LogHealthSignal(BaseModel):
    type: str
    severity: str
    value: Optional[Any] = None
    message: str


class LogHealthEntry(BaseModel):
    log_id: str
    log_name: str
    signals: List[LogHealthSignal]


class LogHealthContextRequest(BaseModel):
    user_id: int
    routine_date: str
    logs: List[LogHealthEntry]


class LogHealthContextResponse(BaseModel):
    success: bool
    message: str
    signals_count: int


class RoutineBriefingResponse(BaseModel):
    briefing_id: str
    mode: str
    narrative: str
    generated_at: str
    model: str


# ------------------------------------------------------------
# Vexy Chat Models
# ------------------------------------------------------------
class ChatContext(BaseModel):
    """
    Comprehensive context provided with chat message.

    Includes market data, positions, trading activity, alerts,
    risk graph state, and UI state for full situational awareness.
    """
    # Market data
    market_data: Optional[Dict[str, Any]] = None

    # User's open positions
    positions: Optional[List[Dict[str, Any]]] = None

    # Trading activity summary
    trading: Optional[Dict[str, Any]] = None

    # Alert state
    alerts: Optional[Dict[str, Any]] = None

    # Risk graph summary
    risk: Optional[Dict[str, Any]] = None

    # Current UI state
    ui: Optional[Dict[str, Any]] = None

    # Legacy fields (for backwards compatibility)
    active_panel: Optional[str] = None
    current_position: Optional[Dict[str, Any]] = None


class VexyChatRequest(BaseModel):
    """Request model for Vexy chat endpoint."""
    message: str
    reflection_dial: float = 0.6
    context: Optional[ChatContext] = None
    user_tier: Optional[str] = None  # Override tier (admin only)


class VexyChatResponse(BaseModel):
    """Response model for Vexy chat endpoint."""
    response: str
    agent: Optional[str] = None
    echo_updated: bool = False
    tokens_used: int = 0
    remaining_today: int = -1


# ------------------------------------------------------------
# Prompt Admin Models
# ------------------------------------------------------------
class PromptUpdateRequest(BaseModel):
    """Request to update a prompt."""
    prompt: str


# ------------------------------------------------------------
# API Endpoints
# ------------------------------------------------------------
@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": SERVICE_NAME}


# ------------------------------------------------------------
# Prompt Admin Endpoints (Admin only)
# ------------------------------------------------------------
@app.get("/api/vexy/admin/prompts")
async def get_all_prompts():
    """
    Get all prompts (outlets and tiers) for admin UI.
    Shows defaults, custom overrides, and which is active.
    """
    from services.vexy_ai.prompt_admin import get_all_prompts as _get_all
    return {"success": True, "data": _get_all()}


@app.get("/api/vexy/admin/prompts/outlet/{outlet}")
async def get_outlet_prompt(outlet: str):
    """Get the active prompt for an outlet (chat, routine, process)."""
    from services.vexy_ai.prompt_admin import get_prompt
    return {"success": True, "outlet": outlet, "prompt": get_prompt(outlet)}


@app.put("/api/vexy/admin/prompts/outlet/{outlet}")
async def set_outlet_prompt(outlet: str, request: PromptUpdateRequest):
    """Set a custom prompt for an outlet."""
    from services.vexy_ai.prompt_admin import set_prompt
    set_prompt(outlet, request.prompt)
    return {"success": True, "outlet": outlet, "message": "Prompt updated"}


@app.delete("/api/vexy/admin/prompts/outlet/{outlet}")
async def reset_outlet_prompt(outlet: str):
    """Reset an outlet to use the default prompt."""
    from services.vexy_ai.prompt_admin import reset_prompt
    reset_prompt(outlet)
    return {"success": True, "outlet": outlet, "message": "Prompt reset to default"}


@app.get("/api/vexy/admin/prompts/tier/{tier}")
async def get_tier_prompt_endpoint(tier: str):
    """Get the active prompt for a tier."""
    from services.vexy_ai.prompt_admin import get_tier_prompt
    return {"success": True, "tier": tier, "prompt": get_tier_prompt(tier)}


@app.put("/api/vexy/admin/prompts/tier/{tier}")
async def set_tier_prompt_endpoint(tier: str, request: PromptUpdateRequest):
    """Set a custom prompt for a tier."""
    from services.vexy_ai.prompt_admin import set_tier_prompt
    set_tier_prompt(tier, request.prompt)
    return {"success": True, "tier": tier, "message": "Prompt updated"}


@app.delete("/api/vexy/admin/prompts/tier/{tier}")
async def reset_tier_prompt_endpoint(tier: str):
    """Reset a tier to use the default prompt."""
    from services.vexy_ai.prompt_admin import reset_tier_prompt
    reset_tier_prompt(tier)
    return {"success": True, "tier": tier, "message": "Prompt reset to default"}


@app.post("/api/vexy/routine-briefing", response_model=RoutineBriefingResponse)
async def routine_briefing(request: RoutineBriefingRequest):
    """
    Generate a Routine Mode orientation briefing.

    Called explicitly by the UI when the Routine drawer opens.
    Vexy does not "watch" the UI - the UI asks for a briefing.
    """
    global _routine_synthesizer

    if _routine_synthesizer is None:
        raise HTTPException(status_code=503, detail="Synthesizer not initialized")

    # Convert Pydantic models to dicts
    payload = {
        "mode": request.mode,
        "timestamp": request.timestamp,
        "market_context": request.market_context.model_dump() if request.market_context else {},
        "user_context": request.user_context.model_dump() if request.user_context else {},
        "open_loops": request.open_loops.model_dump() if request.open_loops else {},
    }

    # Fetch log health signals if user_id provided
    log_health_signals = []
    if request.user_id:
        log_health_signals = get_log_health_signals_for_briefing(request.user_id)

    result = _routine_synthesizer.synthesize(payload, log_health_signals)

    if result is None:
        raise HTTPException(status_code=500, detail="Failed to generate briefing")

    return RoutineBriefingResponse(**result)


# ------------------------------------------------------------
# Routine Panel v1 Endpoints
# ------------------------------------------------------------
class RoutineOrientationRequest(BaseModel):
    """Request model for Routine Orientation (Mode A)."""
    vix_level: Optional[float] = None
    vix_regime: Optional[str] = None


class RoutineOrientationResponse(BaseModel):
    """Response model for Routine Orientation."""
    orientation: Optional[str]  # None = silence is valid
    context_phase: str
    generated_at: str


@app.post("/api/vexy/routine/orientation", response_model=RoutineOrientationResponse)
async def get_routine_orientation(request: RoutineOrientationRequest):
    """
    Get Mode A orientation message for Routine panel.

    May return null orientation (silence is valid).
    Adapts to RoutineContextPhase (weekday/weekend/holiday, time of day).
    """
    from services.vexy_ai.routine_panel import (
        RoutineOrientationGenerator,
        get_routine_context_phase,
    )

    phase = get_routine_context_phase()
    generator = RoutineOrientationGenerator()

    orientation = generator.generate(
        phase=phase,
        vix_level=request.vix_level,
        vix_regime=request.vix_regime,
    )

    return RoutineOrientationResponse(
        orientation=orientation,
        context_phase=phase.value,
        generated_at=datetime.now().isoformat(),
    )


class MarketReadinessResponse(BaseModel):
    """Response model for Market Readiness artifact."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


@app.get("/api/vexy/routine/market-readiness/{user_id}", response_model=MarketReadinessResponse)
async def get_market_readiness(user_id: int):
    """
    Get cached market readiness artifact.

    Generated once or infrequently, not real-time.
    Returns read-only awareness data, not predictions.
    Enforces lexicon constraints (no POC/VAH/VAL).
    """
    from services.vexy_ai.routine_panel import MarketReadinessAggregator

    aggregator = MarketReadinessAggregator(logger=_logger)
    payload = aggregator.aggregate(user_id)

    return MarketReadinessResponse(
        success=True,
        data=payload,
    )


@app.post("/api/vexy/context/log-health", response_model=LogHealthContextResponse)
async def ingest_log_health_context(request: LogHealthContextRequest):
    """
    Ingest log health context for Routine Mode narratives.

    Called by the log_health_analyzer scheduled job at 05:00 ET daily.
    Context is stored per (user_id, routine_date) and is idempotent.

    This endpoint does NOT block or modify logs - it only ingests signals
    for Vexy to surface in Routine briefings.
    """
    try:
        # Store the context
        context = request.model_dump()
        store_routine_context(request.user_id, request.routine_date, context)

        # Count total signals
        total_signals = sum(len(log.signals) for log in request.logs)

        if _logger:
            _logger.info(
                f"Ingested log health context for user {request.user_id}: "
                f"{len(request.logs)} logs, {total_signals} signals",
                emoji="📊"
            )

        return LogHealthContextResponse(
            success=True,
            message=f"Stored context for {request.routine_date}",
            signals_count=total_signals,
        )
    except Exception as e:
        if _logger:
            _logger.error(f"Failed to ingest log health context: {e}", emoji="❌")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/vexy/context/log-health/{user_id}")
async def get_log_health_context(user_id: int, routine_date: Optional[str] = None):
    """
    Retrieve log health context for a user.

    If routine_date is not specified, returns today's context.
    """
    context = get_routine_context(user_id, routine_date)
    if not context:
        return {"success": True, "data": None, "message": "No context available"}

    return {"success": True, "data": context}


@app.get("/api/vexy/process-echo/{user_id}")
async def get_process_echoes(user_id: int):
    """
    Generate Process-Level Echo fragments for a user.

    Returns narrative fragments that connect Routine observations
    to what actually changed during the trading session.

    Per spec:
    - Maximum 1-2 echoes per session
    - Read-only (no state changes)
    - Returns empty if Routine wasn't opened or no meaningful deltas

    Response includes:
    - echoes: List of echo objects with type, message, confidence
    - narrative_fragment: Pre-formatted text for inclusion in Process narrative
    """
    global _process_echo_generator

    if _process_echo_generator is None:
        return {
            "success": True,
            "echoes": [],
            "narrative_fragment": "",
            "message": "Echo generator not initialized"
        }

    try:
        echoes = await _process_echo_generator.generate_echoes(user_id)
        narrative_fragment = format_echoes_for_narrative(echoes)

        if _logger and echoes:
            _logger.info(
                f"Generated {len(echoes)} process echo(es) for user {user_id}",
                emoji="🔄"
            )

        return {
            "success": True,
            "echoes": echoes,
            "narrative_fragment": narrative_fragment,
            "echo_count": len(echoes),
        }
    except Exception as e:
        if _logger:
            _logger.error(f"Failed to generate process echoes: {e}", emoji="❌")
        return {
            "success": False,
            "echoes": [],
            "narrative_fragment": "",
            "error": str(e)
        }


# ------------------------------------------------------------
# Vexy Chat Endpoint
# ------------------------------------------------------------
def _check_rate_limit(user_id: int, tier: str) -> tuple[bool, int]:
    """
    Check if user can send a message based on rate limits.

    Returns (allowed, remaining).
    """
    global _redis_client

    tier_config = get_tier_config(tier)
    limit = tier_config.daily_limit

    # Unlimited for admins
    if limit == -1:
        return True, -1

    if _redis_client is None:
        # Redis not available, allow request but can't track
        return True, limit

    try:
        key = f"vexy_chat:{user_id}:{date.today().isoformat()}"
        current = _redis_client.get(key)
        current_count = int(current) if current else 0

        remaining = max(0, limit - current_count)
        return remaining > 0, remaining
    except Exception:
        # Redis error, allow request
        return True, limit


def _increment_usage(user_id: int) -> None:
    """Increment daily usage counter."""
    global _redis_client

    if _redis_client is None:
        return

    try:
        key = f"vexy_chat:{user_id}:{date.today().isoformat()}"
        _redis_client.incr(key)
        _redis_client.expire(key, 86400 * 2)  # 2 day TTL
    except Exception:
        pass  # Silently ignore Redis errors


def _build_chat_system_prompt(tier: str, user_id: int, user_message: str = "") -> str:
    """
    Build system prompt for chat based on tier.

    Includes:
    - Chat outlet base prompt (conversational, brief) - uses custom if set
    - Tier-specific semantic guardrails - uses custom if set
    - Playbook awareness (tier-gated)
    - Echo Memory context (if enabled)
    """
    from services.vexy_ai.prompt_admin import get_prompt, get_tier_prompt

    tier_config = get_tier_config(tier)

    # Start with Chat outlet base prompt (uses custom if set via admin)
    chat_prompt = get_prompt("chat")
    prompt_parts = [chat_prompt]

    # Add tier-specific semantic scope (uses custom if set via admin)
    tier_prompt = get_tier_prompt(tier)
    prompt_parts.append("\n\n---\n")
    prompt_parts.append(tier_prompt)

    # Add Playbook awareness
    # Include relevant playbooks based on user query + all accessible playbooks
    accessible_playbooks = get_playbooks_for_tier(tier)
    if accessible_playbooks:
        # Find playbooks relevant to the current message
        relevant = find_relevant_playbooks(user_message, tier, max_results=3) if user_message else []

        # Build playbook context
        prompt_parts.append("\n\n---\n")

        if relevant:
            # Highlight relevant playbooks first
            prompt_parts.append("## Relevant Playbooks for This Query\n")
            for pb in relevant:
                prompt_parts.append(f"- **{pb.name}** ({pb.scope}): {pb.description}\n")
            prompt_parts.append("\n")

        # List all accessible playbooks
        prompt_parts.append("## All Accessible Playbooks\n")
        for pb in accessible_playbooks:
            prompt_parts.append(f"- {pb.name} ({pb.scope})\n")

        prompt_parts.append("\n")
        prompt_parts.append("**Instruction:** When relevant, reference these Playbooks by name rather than explaining their content inline. ")
        prompt_parts.append("Playbooks hold structure; you hold presence. Prefer redirection to inline explanation.\n")

    # Add Echo Memory if enabled
    if tier_config.echo_enabled:
        try:
            echo_context = get_echo_context_for_prompt(user_id, days=tier_config.echo_days)
            if echo_context and "No prior Echo" not in echo_context:
                prompt_parts.append("\n\n---\n")
                prompt_parts.append(echo_context)
        except Exception:
            pass  # Echo not available

    return "".join(prompt_parts)


def _format_chat_context(context: Optional[ChatContext]) -> str:
    """
    Format comprehensive chat context for the prompt.

    Includes market data, positions, trading activity, alerts, and UI state.
    """
    if not context:
        return ""

    sections = []

    # Market Data Section
    if context.market_data:
        md = context.market_data
        market_lines = []
        if md.get("spxPrice"):
            spx_str = f"SPX: {md['spxPrice']:.2f}"
            if md.get("spxChangePercent"):
                sign = "+" if md['spxChangePercent'] >= 0 else ""
                spx_str += f" ({sign}{md['spxChangePercent']:.2f}%)"
            market_lines.append(spx_str)
        if md.get("vixLevel"):
            vix_str = f"VIX: {md['vixLevel']:.2f}"
            if md.get("vixRegime"):
                vix_str += f" ({md['vixRegime']})"
            market_lines.append(vix_str)
        if md.get("marketMode"):
            mode_str = f"Market Mode: {md['marketMode']}"
            if md.get("marketModeScore"):
                mode_str += f" (score: {md['marketModeScore']:.0f})"
            market_lines.append(mode_str)
        if md.get("directionalStrength") is not None:
            market_lines.append(f"Directional Strength: {md['directionalStrength']:.2f}")
        if md.get("lfiScore") is not None:
            market_lines.append(f"LFI Score: {md['lfiScore']:.2f}")
        if md.get("gexPosture"):
            market_lines.append(f"GEX Posture: {md['gexPosture']}")

        if market_lines:
            sections.append("## Market Context\n" + "\n".join(market_lines))

    # Positions Section
    if context.positions:
        pos_lines = []
        for pos in context.positions[:5]:  # Limit to 5 most relevant
            pos_str = f"- {pos.get('type', 'position').title()}"
            if pos.get('strikes'):
                pos_str += f" @ {'/'.join(str(s) for s in pos['strikes'])}"
            if pos.get('expiration'):
                pos_str += f" (exp: {pos['expiration'][:10]})"
            if pos.get('daysToExpiry') is not None:
                pos_str += f" [{pos['daysToExpiry']}d]"
            if pos.get('pnl') is not None:
                sign = "+" if pos['pnl'] >= 0 else ""
                pos_str += f" P&L: {sign}${pos['pnl']:.2f}"
            pos_lines.append(pos_str)

        if pos_lines:
            sections.append(f"## Open Positions ({len(context.positions)})\n" + "\n".join(pos_lines))

    # Trading Activity Section
    if context.trading:
        t = context.trading
        trade_lines = []
        if t.get("openTrades"):
            trade_lines.append(f"Open trades: {t['openTrades']}")
        if t.get("todayTrades"):
            trade_lines.append(f"Today's trades: {t['todayTrades']}")
        if t.get("winRate") is not None:
            trade_lines.append(f"Win rate: {t['winRate']}%")
        if t.get("todayPnl") is not None:
            sign = "+" if t['todayPnl'] >= 0 else ""
            trade_lines.append(f"Today's P&L: {sign}${t['todayPnl'] / 100:.2f}")
        if t.get("weekPnl") is not None:
            sign = "+" if t['weekPnl'] >= 0 else ""
            trade_lines.append(f"Week P&L: {sign}${t['weekPnl'] / 100:.2f}")

        if trade_lines:
            sections.append("## Trading Activity\n" + "\n".join(trade_lines))

    # Alerts Section
    if context.alerts:
        a = context.alerts
        alert_lines = []
        if a.get("armed"):
            alert_lines.append(f"Armed alerts: {a['armed']}")
        if a.get("recentTriggers"):
            for trigger in a['recentTriggers'][:3]:
                alert_lines.append(f"- TRIGGERED: {trigger.get('message', 'Alert')} at {trigger.get('triggeredAt', '')}")

        if alert_lines:
            sections.append("## Alerts\n" + "\n".join(alert_lines))

    # Risk Graph Section
    if context.risk and context.risk.get("strategiesOnGraph"):
        r = context.risk
        risk_lines = [f"Strategies on graph: {r['strategiesOnGraph']}"]
        if r.get("totalMaxProfit") is not None:
            risk_lines.append(f"Max profit potential: ${r['totalMaxProfit']:.2f}")
        if r.get("totalMaxLoss") is not None:
            risk_lines.append(f"Max risk: ${abs(r['totalMaxLoss']):.2f}")
        sections.append("## Risk Graph\n" + "\n".join(risk_lines))

    # UI State Section
    if context.ui:
        ui = context.ui
        if ui.get("activePanel"):
            sections.append(f"## Current View\nUser is viewing: {ui['activePanel']}")

    if sections:
        return "\n\n".join(sections)
    return ""


@app.post("/api/vexy/chat", response_model=VexyChatResponse)
async def vexy_chat(request: VexyChatRequest):
    """
    Handle Vexy chat messages.

    Provides direct conversational access to Vexy, the AI engine
    running on The Path OS. Access is tiered by subscription level.
    """
    global _routine_synthesizer, _config

    # For now, default to observer tier (user auth will be handled by gateway)
    # In production, user_id and tier come from auth middleware
    user_id = 1  # TODO: Extract from auth header
    user_tier = request.user_tier or "navigator"  # TODO: Get from auth

    # Validate tier and get config
    tier_config = get_tier_config(user_tier)

    # Check rate limit
    allowed, remaining = _check_rate_limit(user_id, user_tier)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Daily message limit reached ({tier_config.daily_limit} messages)"
        )

    # Validate reflection dial
    reflection_dial = validate_reflection_dial(user_tier, request.reflection_dial)

    # Build system prompt with Playbook awareness based on user message
    system_prompt = _build_chat_system_prompt(user_tier, user_id, request.message)

    # Build user prompt with context
    user_prompt_parts = []

    # Add market context if provided
    context_text = _format_chat_context(request.context)
    if context_text:
        user_prompt_parts.append(context_text)
        user_prompt_parts.append("\n---\n")

    # Add reflection dial guidance
    if reflection_dial <= 0.4:
        user_prompt_parts.append("(Reflection dial: Low. Keep response brief and observational.)\n\n")
    elif reflection_dial >= 0.7:
        user_prompt_parts.append("(Reflection dial: High. Probe deeper, challenge gently.)\n\n")

    # Add user message
    user_prompt_parts.append(request.message)

    user_prompt = "".join(user_prompt_parts)

    # Get API configuration
    env = _config.get("env", {}) or {}
    xai_key = (
        _config.get("XAI_API_KEY") or
        env.get("XAI_API_KEY") or
        os.getenv("XAI_API_KEY") or
        ""
    )
    openai_key = (
        _config.get("OPENAI_API_KEY") or
        env.get("OPENAI_API_KEY") or
        os.getenv("OPENAI_API_KEY") or
        ""
    )

    # Determine API to use (prefer XAI/Grok with Live Search)
    use_xai = bool(xai_key)

    if not xai_key and not openai_key:
        raise HTTPException(status_code=503, detail="No AI API key configured")

    # Call the API
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            if use_xai:
                # Use XAI Responses API with Live Search for real-time awareness
                response = await client.post(
                    "https://api.x.ai/v1/responses",
                    headers={
                        "Authorization": f"Bearer {xai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "grok-4",
                        "instructions": system_prompt,
                        "input": user_prompt,
                        "tools": [
                            {
                                "type": "web_search",
                                "search_parameters": {
                                    "mode": "auto",  # Let Grok decide when to search
                                },
                            }
                        ],
                        "temperature": 0.7,
                    },
                )
            else:
                # Fallback to OpenAI chat/completions
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "max_tokens": 600,
                        "temperature": 0.7,
                    },
                )

            if response.status_code == 429:
                raise HTTPException(status_code=429, detail="AI service rate limited")

            if response.status_code != 200:
                if _logger:
                    _logger.error(f"Chat API error: {response.status_code} - {response.text[:500]}", emoji="❌")
                raise HTTPException(status_code=502, detail="AI service error")

            data = response.json()

            # Parse response based on API type
            if use_xai:
                # XAI Responses API format
                # Response contains 'output' array with message items
                output_items = data.get("output", [])
                narrative_parts = []
                for item in output_items:
                    if item.get("type") == "message":
                        content = item.get("content", [])
                        for c in content:
                            if c.get("type") == "output_text":
                                narrative_parts.append(c.get("text", ""))
                narrative = "\n".join(narrative_parts)
                tokens_used = data.get("usage", {}).get("total_tokens", 0)

                # Log if web search was used
                search_results = [item for item in output_items if item.get("type") == "tool_use"]
                if search_results and _logger:
                    _logger.info(f"Vexy used web search for real-time context", emoji="🌐")
            else:
                # OpenAI chat/completions format
                narrative = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                tokens_used = data.get("usage", {}).get("total_tokens", 0)

            if not narrative:
                raise HTTPException(status_code=502, detail="Empty response from AI")

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI service timeout")
    except HTTPException:
        raise
    except Exception as e:
        if _logger:
            _logger.error(f"Chat error: {e}", emoji="❌")
        raise HTTPException(status_code=500, detail="Internal error")

    # Increment usage after successful response
    _increment_usage(user_id)

    # Calculate remaining after this message
    _, remaining_after = _check_rate_limit(user_id, user_tier)

    if _logger:
        _logger.info(f"Chat response for user {user_id}: {len(narrative)} chars", emoji="🦋")

    return VexyChatResponse(
        response=narrative.strip(),
        agent=None,  # TODO: Detect agent from response
        echo_updated=False,  # TODO: Implement echo update
        tokens_used=tokens_used,
        remaining_today=remaining_after if remaining_after >= 0 else -1,
    )


# ------------------------------------------------------------
# Journal Endpoints
# ------------------------------------------------------------
class JournalSynopsisRequest(BaseModel):
    """Request model for generating a Daily Synopsis."""
    trade_date: str  # ISO date string YYYY-MM-DD
    trades: List[Dict[str, Any]]
    market_context: Optional[str] = None  # e.g., "CPI released pre-market"


class JournalSynopsisResponse(BaseModel):
    """Response model for Daily Synopsis."""
    synopsis_text: str
    activity: Optional[Dict[str, Any]] = None
    rhythm: Optional[Dict[str, Any]] = None
    risk_exposure: Optional[Dict[str, Any]] = None
    context: Optional[str] = None


class JournalPromptsResponse(BaseModel):
    """Response model for reflective prompts."""
    prompts: List[Dict[str, str]]
    should_vexy_speak: bool
    vexy_reflection: Optional[str] = None


class JournalChatRequest(BaseModel):
    """Request for Vexy chat in Journal context."""
    message: str
    trade_date: str  # ISO date string
    trades: List[Dict[str, Any]]
    market_context: Optional[str] = None
    is_prepared_prompt: bool = False  # True if clicking a prepared prompt


@app.post("/api/vexy/journal/synopsis", response_model=JournalSynopsisResponse)
async def journal_synopsis(request: JournalSynopsisRequest):
    """
    Generate the Daily Synopsis for the Journal.

    The Synopsis is a weather report, not a scorecard.
    """
    from services.vexy_ai.journal_prompts import (
        build_daily_synopsis,
        format_synopsis_text,
    )
    from datetime import datetime

    try:
        trade_date = datetime.fromisoformat(request.trade_date).date()
    except ValueError:
        trade_date = date.today()

    synopsis = build_daily_synopsis(
        trade_date=trade_date,
        trades=request.trades,
        market_context=request.market_context,
    )

    return JournalSynopsisResponse(
        synopsis_text=format_synopsis_text(synopsis),
        activity=synopsis.activity,
        rhythm=synopsis.rhythm,
        risk_exposure=synopsis.risk_exposure,
        context=synopsis.context,
    )


@app.post("/api/vexy/journal/prompts", response_model=JournalPromptsResponse)
async def journal_prompts(request: JournalSynopsisRequest):
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
    from datetime import datetime

    try:
        trade_date = datetime.fromisoformat(request.trade_date).date()
    except ValueError:
        trade_date = date.today()

    synopsis = build_daily_synopsis(
        trade_date=trade_date,
        trades=request.trades,
        market_context=request.market_context,
    )

    # Generate prepared prompts
    prompts = generate_reflective_prompts(synopsis, request.trades)
    prompt_dicts = [
        {
            "text": p.text,
            "category": p.category.value,
            "grounded_in": p.grounded_in or "",
        }
        for p in prompts
    ]

    # Check if Vexy should speak unprompted
    speak, reflection = should_vexy_speak(synopsis, request.trades)

    return JournalPromptsResponse(
        prompts=prompt_dicts,
        should_vexy_speak=speak,
        vexy_reflection=reflection,
    )


@app.post("/api/vexy/journal/chat")
async def journal_chat(request: JournalChatRequest):
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
    from datetime import datetime

    try:
        trade_date = datetime.fromisoformat(request.trade_date).date()
    except ValueError:
        trade_date = date.today()

    synopsis = build_daily_synopsis(
        trade_date=trade_date,
        trades=request.trades,
        market_context=request.market_context,
    )

    # Build Journal-specific system prompt
    mode = "prepared" if request.is_prepared_prompt else "direct"
    system_prompt = get_journal_prompt(
        synopsis=synopsis,
        trades=request.trades,
        mode=mode,
        prepared_prompt_text=request.message if request.is_prepared_prompt else None,
    )

    # Get API key
    env = _config.get("env", {}) or {}
    xai_key = (
        _config.get("XAI_API_KEY") or
        env.get("XAI_API_KEY") or
        os.getenv("XAI_API_KEY") or
        ""
    )
    openai_key = (
        _config.get("OPENAI_API_KEY") or
        env.get("OPENAI_API_KEY") or
        os.getenv("OPENAI_API_KEY") or
        ""
    )

    use_xai = bool(xai_key)

    if not xai_key and not openai_key:
        raise HTTPException(status_code=503, detail="No AI API key configured")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if use_xai:
                response = await client.post(
                    "https://api.x.ai/v1/responses",
                    headers={
                        "Authorization": f"Bearer {xai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "grok-4",
                        "instructions": system_prompt,
                        "input": request.message,
                        "temperature": 0.6,  # Slightly lower for Journal's neutral tone
                    },
                )
            else:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": request.message},
                        ],
                        "max_tokens": 400,  # Shorter for Journal's brevity
                        "temperature": 0.6,
                    },
                )

            if response.status_code != 200:
                if _logger:
                    _logger.error(f"Journal chat API error: {response.status_code}", emoji="❌")
                raise HTTPException(status_code=502, detail="AI service error")

            data = response.json()

            if use_xai:
                output_items = data.get("output", [])
                narrative_parts = []
                for item in output_items:
                    if item.get("type") == "message":
                        content = item.get("content", [])
                        for c in content:
                            if c.get("type") == "output_text":
                                narrative_parts.append(c.get("text", ""))
                narrative = "\n".join(narrative_parts)
            else:
                narrative = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not narrative:
                raise HTTPException(status_code=502, detail="Empty response from AI")

            if _logger:
                _logger.info(f"Journal chat response: {len(narrative)} chars", emoji="📓")

            return {
                "response": narrative.strip(),
                "mode": mode,
            }

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI service timeout")
    except HTTPException:
        raise
    except Exception as e:
        if _logger:
            _logger.error(f"Journal chat error: {e}", emoji="❌")
        raise HTTPException(status_code=500, detail="Internal error")


# ------------------------------------------------------------
# Playbook Authoring Endpoints
# ------------------------------------------------------------
class MarkFodderRequest(BaseModel):
    """Request to mark content as Playbook material."""
    source: str  # journal, retrospective, ml_pattern, trade, manual
    source_id: str
    content: str
    source_label: Optional[str] = None
    source_date: Optional[str] = None  # ISO date string


class PlaybookFodderResponse(BaseModel):
    """Response with fodder item."""
    id: str
    source: str
    content: str
    source_label: Optional[str] = None
    marked_at: str


class CreatePlaybookRequest(BaseModel):
    """Request to create a playbook from fodder."""
    fodder_ids: List[str]
    name: str = "Untitled"


class UpdatePlaybookRequest(BaseModel):
    """Request to update playbook content."""
    name: Optional[str] = None
    sections: Optional[Dict[str, str]] = None
    state: Optional[str] = None  # draft, active, archived


class PlaybookChatRequest(BaseModel):
    """Request for Vexy assistance during playbook authoring."""
    message: str
    fodder_items: List[Dict[str, Any]]  # Current fodder being worked with
    current_sections: Optional[Dict[str, str]] = None


@app.get("/api/vexy/playbook/sections")
async def get_playbook_sections():
    """
    Get the canonical playbook sections with prompts.

    All sections are optional - none are required.
    """
    from services.vexy_ai.playbook_authoring import SECTION_PROMPTS, PlaybookSection

    sections = []
    for section in PlaybookSection:
        info = SECTION_PROMPTS.get(section, {})
        sections.append({
            "key": section.value,
            "title": info.get("title", section.value.replace("_", " ").title()),
            "prompt": info.get("prompt", ""),
            "description": info.get("description", ""),
        })

    return {"sections": sections}


@app.get("/api/vexy/playbook/ui-guidance")
async def get_playbook_ui_guidance():
    """
    Get UI guidance for playbook authoring surface.

    Includes visual treatment, layout, and anti-patterns.
    """
    from services.vexy_ai.playbook_authoring import PLAYBOOK_UI_GUIDANCE

    return PLAYBOOK_UI_GUIDANCE


@app.post("/api/vexy/playbook/fodder")
async def mark_fodder(request: MarkFodderRequest, user_id: int = 1):
    """
    Mark content as Playbook material (fodder).

    This does NOT create a Playbook - it creates fodder.
    Playbooks are never created from an empty state.
    """
    from services.vexy_ai.playbook_authoring import PlaybookFodder, FodderSource
    from datetime import datetime

    try:
        source = FodderSource(request.source)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid source: {request.source}")

    source_date = None
    if request.source_date:
        try:
            source_date = datetime.fromisoformat(request.source_date)
        except ValueError:
            pass

    fodder = PlaybookFodder.create(
        user_id=user_id,
        source=source,
        source_id=request.source_id,
        content=request.content,
        source_date=source_date,
        source_label=request.source_label,
    )

    if _logger:
        _logger.info(f"Marked fodder from {source.value}: {fodder.id[:8]}...", emoji="🌿")

    return PlaybookFodderResponse(
        id=fodder.id,
        source=fodder.source.value,
        content=fodder.content,
        source_label=fodder.source_label,
        marked_at=fodder.marked_at.isoformat(),
    )


@app.post("/api/vexy/playbook/authoring-prompt")
async def get_authoring_prompt_endpoint(fodder_items: List[Dict[str, Any]]):
    """
    Get the authoring prompt for a set of fodder items.

    Returns the initial prompt: "Here are the moments you marked. What connects them?"
    """
    from services.vexy_ai.playbook_authoring import (
        PlaybookFodder,
        FodderSource,
        get_authoring_prompt,
    )
    from datetime import datetime

    # Convert dict items to PlaybookFodder objects
    fodder_objs = []
    for item in fodder_items:
        try:
            fodder = PlaybookFodder(
                id=item.get("id", ""),
                user_id=item.get("user_id", 1),
                source=FodderSource(item.get("source", "manual")),
                source_id=item.get("source_id", ""),
                content=item.get("content", ""),
                created_at=datetime.now(),
                marked_at=datetime.now(),
                source_label=item.get("source_label"),
            )
            fodder_objs.append(fodder)
        except Exception:
            continue

    prompt = get_authoring_prompt(fodder_objs)
    return {"prompt": prompt}


@app.post("/api/vexy/playbook/chat")
async def playbook_chat(request: PlaybookChatRequest):
    """
    Handle Vexy chat during playbook authoring.

    Vexy may:
    - Reflect similarities across fodder
    - Point out repeated language
    - Ask clarifying questions
    - Suggest consolidation

    Vexy must NOT:
    - Write the Playbook
    - Suggest optimization
    - Prescribe improvements
    """
    from services.vexy_ai.playbook_authoring import (
        PlaybookFodder,
        FodderSource,
        get_vexy_playbook_prompt,
        validate_vexy_response,
    )
    from datetime import datetime

    # Convert dict items to PlaybookFodder objects
    fodder_objs = []
    for item in request.fodder_items:
        try:
            fodder = PlaybookFodder(
                id=item.get("id", ""),
                user_id=item.get("user_id", 1),
                source=FodderSource(item.get("source", "manual")),
                source_id=item.get("source_id", ""),
                content=item.get("content", ""),
                created_at=datetime.now(),
                marked_at=datetime.now(),
                source_label=item.get("source_label"),
            )
            fodder_objs.append(fodder)
        except Exception:
            continue

    # Build system prompt
    system_prompt = get_vexy_playbook_prompt(fodder_objs)

    # Add current sections context if provided
    if request.current_sections:
        sections_text = "\n## Current Draft Sections\n"
        for section, content in request.current_sections.items():
            if content:
                sections_text += f"\n**{section.replace('_', ' ').title()}:**\n{content[:300]}...\n"
        system_prompt += sections_text

    # Get API key
    env = _config.get("env", {}) or {}
    xai_key = (
        _config.get("XAI_API_KEY") or
        env.get("XAI_API_KEY") or
        os.getenv("XAI_API_KEY") or
        ""
    )
    openai_key = (
        _config.get("OPENAI_API_KEY") or
        env.get("OPENAI_API_KEY") or
        os.getenv("OPENAI_API_KEY") or
        ""
    )

    use_xai = bool(xai_key)

    if not xai_key and not openai_key:
        raise HTTPException(status_code=503, detail="No AI API key configured")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if use_xai:
                response = await client.post(
                    "https://api.x.ai/v1/responses",
                    headers={
                        "Authorization": f"Bearer {xai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "grok-4",
                        "instructions": system_prompt,
                        "input": request.message,
                        "temperature": 0.5,  # Lower for calm, sparse responses
                    },
                )
            else:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": request.message},
                        ],
                        "max_tokens": 300,  # Shorter for sparse voice
                        "temperature": 0.5,
                    },
                )

            if response.status_code != 200:
                if _logger:
                    _logger.error(f"Playbook chat API error: {response.status_code}", emoji="❌")
                raise HTTPException(status_code=502, detail="AI service error")

            data = response.json()

            if use_xai:
                output_items = data.get("output", [])
                narrative_parts = []
                for item in output_items:
                    if item.get("type") == "message":
                        content = item.get("content", [])
                        for c in content:
                            if c.get("type") == "output_text":
                                narrative_parts.append(c.get("text", ""))
                narrative = "\n".join(narrative_parts)
            else:
                narrative = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not narrative:
                raise HTTPException(status_code=502, detail="Empty response from AI")

            # Validate response doesn't contain forbidden language
            violations = validate_vexy_response(narrative)
            if violations and _logger:
                _logger.warn(f"Playbook response had violations: {violations}", emoji="⚠️")

            if _logger:
                _logger.info(f"Playbook chat response: {len(narrative)} chars", emoji="🌿")

            return {
                "response": narrative.strip(),
                "violations": violations,  # Include for debugging
            }

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI service timeout")
    except HTTPException:
        raise
    except Exception as e:
        if _logger:
            _logger.error(f"Playbook chat error: {e}", emoji="❌")
        raise HTTPException(status_code=500, detail="Internal error")


# ------------------------------------------------------------
# Playbook Extraction Endpoints (Retro → Playbook)
# ------------------------------------------------------------
class CheckExtractionRequest(BaseModel):
    """Request to check if content is eligible for extraction."""
    content: str


class CheckExtractionResponse(BaseModel):
    """Response with extraction eligibility."""
    eligible: bool
    positive_signals: List[str]
    negative_signals: List[str]
    reason: str


class ProposeExtractionRequest(BaseModel):
    """Request to propose extraction from retrospective."""
    retro_id: str
    phase_content: Dict[str, str]  # phase_name -> content


class ExtractionCandidateResponse(BaseModel):
    """Response with extraction candidate."""
    candidate_id: str
    confidence: str
    supporting_quotes: List[str]
    vexy_observation: Optional[str]
    actions: List[str]


class PromoteCandidateRequest(BaseModel):
    """Request to promote candidate to playbook."""
    candidate_id: str
    title: Optional[str] = None
    initial_content: Optional[str] = None


@app.post("/api/vexy/extraction/check", response_model=CheckExtractionResponse)
async def check_extraction_eligibility(request: CheckExtractionRequest):
    """
    Check if content contains language signals eligible for extraction.

    Positive signals: recurrence, contrast, identity-level noticing
    Negative signals: prescription, optimization, "should" language

    Extraction blocked if negative signals present.
    """
    from services.vexy_ai.playbook_extraction import detect_extraction_eligibility

    eligible, positive, negative = detect_extraction_eligibility(request.content)

    if negative:
        reason = f"Prescription language blocks extraction: {negative[0]}"
    elif not positive:
        reason = "No pattern/recurrence language detected"
    else:
        reason = f"Pattern language detected: {positive[0]}"

    return CheckExtractionResponse(
        eligible=eligible,
        positive_signals=positive,
        negative_signals=negative,
        reason=reason,
    )


@app.post("/api/vexy/extraction/propose", response_model=ExtractionCandidateResponse)
async def propose_extraction(request: ProposeExtractionRequest, user_id: int = 1):
    """
    Propose extraction from retrospective content.

    Creates a PlaybookCandidate (draft, not yet a Playbook).
    Returns preview with Vexy's gentle observation.

    Extraction is offered, not performed.
    """
    from services.vexy_ai.playbook_extraction import (
        PlaybookCandidate,
        should_propose_extraction,
        create_extraction_preview,
    )

    # Check if extraction should be proposed
    should, reason = should_propose_extraction(request.phase_content)

    if not should:
        raise HTTPException(
            status_code=400,
            detail=f"Extraction not eligible: {reason}"
        )

    # Create candidate
    candidate = PlaybookCandidate.create_from_retro(
        user_id=user_id,
        retro_id=request.retro_id,
        phase_content=request.phase_content,
    )

    # Create preview
    preview = create_extraction_preview(candidate)

    if _logger:
        _logger.info(
            f"Extraction proposed: {candidate.id[:8]}... ({candidate.confidence.value})",
            emoji="🌿"
        )

    return ExtractionCandidateResponse(
        candidate_id=candidate.id,
        confidence=candidate.confidence.value,
        supporting_quotes=candidate.supporting_quotes,
        vexy_observation=preview.vexy_observation,
        actions=preview.actions,
    )


@app.get("/api/vexy/extraction/ui-guidance")
async def get_extraction_ui_guidance_endpoint():
    """
    Get UI guidance for extraction preview.

    Key rules:
    - Read-only by default
    - Soft edges, low contrast
    - No "Create", "Save", or "Finish" buttons
    - Dismissal leaves no trace
    """
    from services.vexy_ai.playbook_extraction import get_extraction_ui_guidance
    return get_extraction_ui_guidance()


@app.post("/api/vexy/extraction/promote")
async def promote_candidate(request: PromoteCandidateRequest, user_id: int = 1):
    """
    Promote a candidate to a full Playbook.

    Promotion rules:
    - No minimum length
    - No required structure
    - Empty Playbook is valid
    - Title without content is valid
    """
    from services.vexy_ai.playbook_extraction import (
        PlaybookCandidate,
        ExtractionSource,
        ExtractionTrigger,
        ExtractionConfidence,
        promote_candidate_to_playbook,
    )

    # In production, fetch candidate from storage
    # For now, create a minimal candidate to demonstrate promotion
    candidate = PlaybookCandidate(
        id=request.candidate_id,
        user_id=user_id,
        source_type=ExtractionSource.RETROSPECTIVE,
        source_ids=[],
        trigger=ExtractionTrigger.MANUAL_MARK,
        created_at=datetime.now(),
        confidence=ExtractionConfidence.EMERGING,
        supporting_quotes=[request.initial_content] if request.initial_content else [],
    )

    result = promote_candidate_to_playbook(
        candidate=candidate,
        title=request.title,
        initial_content=request.initial_content,
    )

    if _logger:
        _logger.info(
            f"Candidate promoted to Playbook: {result['playbook_id'][:8]}...",
            emoji="🌿"
        )

    return {
        "success": True,
        **result,
    }


@app.post("/api/vexy/extraction/observe")
async def get_extraction_observation(phase_content: Dict[str, str]):
    """
    Get Vexy's gentle observation for potential extraction.

    Returns None if uncertain — silence is preferred.
    """
    from services.vexy_ai.playbook_extraction import (
        detect_extraction_eligibility,
        get_extraction_observation as _get_observation,
        ExtractionConfidence,
    )

    all_content = " ".join(phase_content.values())
    eligible, positive, negative = detect_extraction_eligibility(all_content)

    if not eligible:
        return {"observation": None, "reason": "Not eligible for extraction"}

    # Determine confidence
    confidence = ExtractionConfidence.LOW
    if len(positive) >= 3:
        confidence = ExtractionConfidence.CLEAR
    elif len(positive) >= 1:
        confidence = ExtractionConfidence.EMERGING

    # Count meaningful quotes
    quote_count = sum(1 for v in phase_content.values() if v and len(v.strip()) > 20)

    observation = _get_observation(confidence, quote_count)

    return {
        "observation": observation,
        "confidence": confidence.value,
        "eligible": True,
    }


# ------------------------------------------------------------
# ML Thresholds Endpoints
# ------------------------------------------------------------
class MLStatusRequest(BaseModel):
    """Request for ML status check."""
    retrospective_count: int
    closed_trade_count: int
    distinct_period_count: int


class PatternEligibilityRequest(BaseModel):
    """Request to check pattern eligibility."""
    pattern_type: str
    sources: List[str]
    artifact_count: int
    is_template_induced: bool = False


class PatternConfirmationRequest(BaseModel):
    """Request for ML pattern confirmation."""
    pattern_id: str
    occurrences: int
    retrospective_count: int
    days_span: int
    similarity_score: float
    contradiction_ratio: float = 0.0
    market_regimes: int = 1
    stability_score: float = 0.5
    description_variance: float = 0.5
    user_has_playbooks: bool = False
    context: str = "retrospective"


@app.post("/api/vexy/ml/status")
async def get_ml_status(request: MLStatusRequest):
    """
    Get ML confirmation status for a user.

    ML is disabled until baseline requirements are met:
    - ≥5 completed retrospectives
    - ≥20 closed trades
    - ≥2 distinct periods
    """
    from services.vexy_ai.ml_thresholds import get_ml_status_for_user

    return get_ml_status_for_user(
        request.retrospective_count,
        request.closed_trade_count,
        request.distinct_period_count,
    )


@app.get("/api/vexy/ml/thresholds")
async def get_ml_thresholds():
    """
    Get ML confirmation thresholds.

    These are exploratory defaults, explicitly marked for revision.
    """
    from services.vexy_ai.ml_thresholds import get_threshold_summary

    return {
        "status": "provisional",
        "thresholds": get_threshold_summary(),
        "doctrine": {
            "ml_is_confirmatory": True,
            "ml_never_names_patterns": True,
            "ml_never_recommends_actions": True,
            "ml_never_escalates_urgency": True,
            "silence_is_always_valid": True,
            "human_outranks_model": True,
        },
    }


@app.post("/api/vexy/ml/pattern-eligible")
async def check_pattern_eligibility(request: PatternEligibilityRequest):
    """
    Check if a pattern is eligible for ML confirmation.

    Eligibility requires:
    1. Appears in human-generated text (journal, retro)
    2. Appears across multiple artifacts
    3. Not template-induced
    4. Behavioral/contextual, not outcome-based

    Disallowed: P&L patterns, strategy performance, predictions
    """
    from services.vexy_ai.ml_thresholds import is_pattern_eligible

    eligible, reason = is_pattern_eligible(
        request.pattern_type,
        request.sources,
        request.artifact_count,
        request.is_template_induced,
    )

    return {
        "eligible": eligible,
        "reason": reason,
    }


@app.post("/api/vexy/ml/confirm")
async def get_ml_confirmation(request: PatternConfirmationRequest, user_id: int = 1):
    """
    Get ML confirmation for a pattern if thresholds are met.

    Returns confirmation text only if:
    - Baseline requirements met
    - Pattern meets confidence thresholds
    - Context allows ML output
    - No active override exists

    ML may return None (silence) - this is valid and expected.
    """
    from services.vexy_ai.ml_thresholds import (
        PatternMetrics,
        create_ml_confirmation,
        check_baseline_requirements,
        MLConfidenceLevel,
    )

    # For demo, assume baseline is met if we have any metrics
    # In production, this would check actual user data
    baseline_met = request.retrospective_count >= 5

    metrics = PatternMetrics(
        occurrences=request.occurrences,
        retrospective_count=request.retrospective_count,
        days_span=request.days_span,
        similarity_score=request.similarity_score,
        contradiction_ratio=request.contradiction_ratio,
        market_regimes=request.market_regimes,
        stability_score=request.stability_score,
        description_variance=request.description_variance,
        user_has_playbooks=request.user_has_playbooks,
    )

    confirmation = create_ml_confirmation(
        pattern_id=request.pattern_id,
        user_id=user_id,
        metrics=metrics,
        context=request.context,
        baseline_met=baseline_met,
        overrides=[],  # In production, load from storage
    )

    if confirmation is None:
        return {
            "output": None,
            "reason": "ML chose silence (insufficient confidence or context not allowed)",
            "confidence_level": None,
        }

    return {
        "output": confirmation.output_text,
        "confidence_level": confirmation.confidence_level.name,
        "confidence_value": confirmation.confidence_level.value,
    }


@app.get("/api/vexy/ml/allowed-contexts")
async def get_ml_allowed_contexts():
    """
    Get contexts where ML confirmation is allowed vs forbidden.

    Allowed: retrospective, journal_reflection, process_echo
    Forbidden: live_trading, execution, alert_handling, market_stress
    """
    from services.vexy_ai.ml_thresholds import (
        ALLOWED_ML_CONTEXTS,
        FORBIDDEN_ML_CONTEXTS,
    )

    return {
        "allowed": list(ALLOWED_ML_CONTEXTS),
        "forbidden": list(FORBIDDEN_ML_CONTEXTS),
        "rule": "ML confirmation is NEVER shown during live trading, execution, or market stress",
    }


@app.get("/api/vexy/ml/language-rules")
async def get_ml_language_rules():
    """
    Get language constraints for ML confirmations.

    ML follows Process Echo rules, not Alert rules.
    """
    from services.vexy_ai.ml_thresholds import (
        ML_ALLOWED_PHRASES,
        ML_FORBIDDEN_PHRASES,
    )

    return {
        "allowed_phrases": ML_ALLOWED_PHRASES,
        "forbidden_phrases": ML_FORBIDDEN_PHRASES,
        "rule": "If ML 'wants' to explain, it must remain silent",
    }


# ------------------------------------------------------------
# HTTP Server Runner
# ------------------------------------------------------------
async def run_http_server():
    """Run the FastAPI server using uvicorn."""
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=HTTP_PORT,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


# ------------------------------------------------------------
# Main lifecycle
# ------------------------------------------------------------
async def main():
    global _config, _logger, _routine_synthesizer, _process_echo_generator

    # -------------------------------------------------
    # Phase 1: bootstrap logger
    # -------------------------------------------------
    _logger = LogUtil(SERVICE_NAME)
    _logger.info("starting setup()", emoji="⚙️")

    # -------------------------------------------------
    # Load configuration
    # -------------------------------------------------
    setup = SetupBase(SERVICE_NAME, _logger)
    _config = await setup.load()

    # Promote logger (config-driven)
    _logger.configure_from_config(_config)
    _logger.ok("configuration loaded", emoji="📄")

    # -------------------------------------------------
    # Initialize Routine Briefing Synthesizer
    # -------------------------------------------------
    _routine_synthesizer = RoutineBriefingSynthesizer(_config, _logger)
    _logger.info(f"Routine briefing synthesizer initialized", emoji="🌅")

    # -------------------------------------------------
    # Initialize Process Echo Generator
    # -------------------------------------------------
    journal_api_base = _config.get("JOURNAL_API_BASE", os.getenv("JOURNAL_API_BASE", "http://localhost:3001"))
    _process_echo_generator = ProcessEchoGenerator(journal_api_base, _logger)
    _logger.info(f"Process echo generator initialized", emoji="🔄")

    # -------------------------------------------------
    # Initialize Redis for rate limiting (optional)
    # -------------------------------------------------
    global _redis_client
    redis_url = _config.get("REDIS_URL") or os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        _redis_client = redis.from_url(redis_url)
        _redis_client.ping()
        _logger.info("Redis connected for rate limiting", emoji="🔴")
    except Exception as e:
        _logger.warn(f"Redis not available, rate limiting disabled: {e}", emoji="⚠️")
        _redis_client = None

    # -------------------------------------------------
    # Start threaded heartbeat (OUTSIDE asyncio)
    # -------------------------------------------------
    hb_stop = start_heartbeat(
        SERVICE_NAME,
        _config,
        _logger,
        payload_fn=lambda: {
            "service": SERVICE_NAME,
            "mode": "assistant",
            "http_port": HTTP_PORT,
        },
    )

    # -------------------------------------------------
    # Start both orchestrator and HTTP server
    # -------------------------------------------------
    _logger.info(f"Starting HTTP server on port {HTTP_PORT}", emoji="🌐")

    orch_task = asyncio.create_task(
        orchestrator_run(_config, _logger),
        name=f"{SERVICE_NAME}-orchestrator",
    )

    http_task = asyncio.create_task(
        run_http_server(),
        name=f"{SERVICE_NAME}-http",
    )

    try:
        # Wait for either task to complete (or fail)
        done, pending = await asyncio.wait(
            [orch_task, http_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Log which task finished
        for task in done:
            if task.exception():
                _logger.error(f"Task {task.get_name()} failed: {task.exception()}", emoji="❌")
            else:
                _logger.warn(f"Task {task.get_name()} exited unexpectedly", emoji="⚠️")

        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    finally:
        # Always stop heartbeat thread
        hb_stop.set()


# ------------------------------------------------------------
# Runtime wrapper: ensures clean Ctrl-C handling
# ------------------------------------------------------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down gracefully…")