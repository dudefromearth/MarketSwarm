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

# FastAPI for HTTP endpoints
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import uvicorn


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


class RoutineBriefingResponse(BaseModel):
    briefing_id: str
    mode: str
    narrative: str
    generated_at: str
    model: str


# ------------------------------------------------------------
# API Endpoints
# ------------------------------------------------------------
@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": SERVICE_NAME}


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

    result = _routine_synthesizer.synthesize(payload)

    if result is None:
        raise HTTPException(status_code=500, detail="Failed to generate briefing")

    return RoutineBriefingResponse(**result)


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
    global _config, _logger, _routine_synthesizer

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