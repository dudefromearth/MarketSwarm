"""
Copilot Service - MEL + ADI + AI Commentary

Entry point. Bootstraps the service and hands off to orchestrators.
"""

import asyncio
import logging
import signal
import os
import sys
from pathlib import Path
from datetime import datetime

from aiohttp import web
import aiohttp_cors

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from intel.mel import MELOrchestrator
from intel.mel_models import MELConfig
from intel.mel_api import MELAPIHandler
from intel.adi import ADIOrchestrator
from intel.adi_api import ADIAPIHandler
from intel.commentary import CommentaryService
from intel.commentary_models import CommentaryConfig
from intel.commentary_api import CommentaryAPIHandler
from intel.ai_providers import AIProviderConfig


# Configuration
HOST = os.environ.get("COPILOT_HOST", "127.0.0.1")
PORT = int(os.environ.get("COPILOT_PORT", "8095"))
LOG_LEVEL = os.environ.get("COPILOT_LOG_LEVEL", "INFO")


# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("copilot")


async def health_check(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.json_response({
        "status": "ok",
        "service": "copilot",
        "timestamp": datetime.utcnow().isoformat(),
    })


def get_market_data() -> dict:
    """
    Get current market data for MEL calculation.

    TODO: Integrate with MarketSwarm Redis/massive pipeline.
    """
    return {
        "spot_price": None,
        "gamma_levels": None,
        "volume_profile": None,
        "timestamp": datetime.utcnow(),
    }


def get_event_flags(now: datetime) -> list:
    """
    Get event flags for the current time.

    TODO: Integrate with economic calendar.
    """
    return []


def get_user_context() -> dict:
    """
    Get user context for ADI snapshot.

    TODO: Integrate with UI state (selected tile, alerts, trades).
    """
    return {
        "selected_tile": None,
        "risk_graph_strategies": [],
        "active_alerts": [],
        "open_trades": [],
        "active_log_id": None,
    }


async def main():
    """Main entry point - bootstrap and hand off."""
    logger.info("Starting Copilot Service...")

    # Create MEL orchestrator
    config = MELConfig()
    mel = MELOrchestrator(
        config=config,
        logger=logger,
        market_data_provider=get_market_data,
        event_calendar=get_event_flags,
    )

    # Create MEL API handler
    mel_api = MELAPIHandler(orchestrator=mel, logger=logger)

    # Create ADI orchestrator (uses MEL for scores)
    adi = ADIOrchestrator(
        mel_orchestrator=mel,
        market_data_provider=get_market_data,
        user_context_provider=get_user_context,
        logger=logger,
        symbol="SPX",
    )

    # Create ADI API handler
    adi_api = ADIAPIHandler(orchestrator=adi, logger=logger)

    # Create Commentary service (AI provider abstraction)
    ai_config = AIProviderConfig(
        provider=os.environ.get("AI_PROVIDER", "openai"),
        api_key=os.environ.get("OPENAI_API_KEY"),
        model=os.environ.get("AI_MODEL"),
    )
    commentary_config = CommentaryConfig()
    commentary = CommentaryService(
        config=commentary_config,
        ai_config=ai_config,
        logger=logger,
    )

    # Create Commentary API handler
    commentary_api = CommentaryAPIHandler(service=commentary, logger=logger)

    # Connect MEL updates to Commentary triggers
    mel.subscribe(commentary.update_mel)

    # Setup web app
    app = web.Application()
    app.router.add_get("/health", health_check)
    mel_api.register_routes(app)
    adi_api.register_routes(app)
    commentary_api.register_routes(app)

    # Setup CORS
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })
    for route in list(app.router.routes()):
        if not route.resource.canonical.startswith("/ws"):
            cors.add(route)

    # Setup shutdown handler
    async def shutdown():
        logger.info("Shutting down...")
        await commentary.stop()
        await mel.stop()
        await mel_api.close_all()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

    # Start MEL orchestrator
    mel_api.setup_broadcast()
    await mel.start()

    # Start Commentary service
    await commentary.start()

    # Start web server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()

    logger.info(f"Copilot Service ready at http://{HOST}:{PORT}")

    # Keep running
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
