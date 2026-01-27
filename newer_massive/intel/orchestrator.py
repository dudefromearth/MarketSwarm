import asyncio
from typing import Dict, Any

from .spot_worker import SpotWorker
from .chain_worker import ChainWorker
from .ws_worker import WsWorker
from .ws_hydrator import WsHydrator
from .replay_worker import ReplayWorker

from ..model_builders.heatmap import HeatmapModelBuilder
from ..model_builders.gex import GexModelBuilder


async def run(config: Dict[str, Any], logger) -> None:
    """
    Massive orchestrator — wiring and lifecycle control.
    Must never crash the process.
    """
    stop_event = asyncio.Event()
    tasks = []

    ws_replay = config.get("MASSIVE_WS_REPLAY", "false").lower() == "true"
    ws_enabled = config.get("MASSIVE_WS_ENABLED", "true").lower() == "true"

    try:
        if ws_replay:
            replay = ReplayWorker(config, logger)
            tasks.append(
                asyncio.create_task(replay.run(stop_event), name="massive-replay")
            )
            logger.info("orchestrator starting (REPLAY mode)", emoji="🎞️")

        else:
            # --------------------------------------------------
            # Always-on workers
            # --------------------------------------------------
            spot = SpotWorker(config, logger)
            chain = ChainWorker(config, logger)
            heatmap = HeatmapModelBuilder(config, logger)
            gex = GexModelBuilder(config, logger)

            tasks.extend(
                [
                    asyncio.create_task(spot.run(stop_event), name="massive-spot"),
                    asyncio.create_task(chain.run(stop_event), name="massive-chain"),
                    asyncio.create_task(
                        heatmap.run(stop_event), name="massive-heatmap"
                    ),
                    asyncio.create_task(
                        gex.run(stop_event), name="massive-gex"
                    ),
                ]
            )

            if ws_enabled:
                ws = WsWorker(config, logger)
                hydrator = WsHydrator(config, logger)

                tasks.extend(
                    [
                        asyncio.create_task(ws.run(stop_event), name="massive-ws"),
                        asyncio.create_task(
                            hydrator.run(stop_event), name="massive-ws-hydrator"
                        ),
                    ]
                )

                logger.info(
                    "orchestrator starting (spot + chain + heatmap + gex + ws + hydrator)",
                    emoji="🚀",
                )
            else:
                logger.info(
                    "orchestrator starting (spot + chain + heatmap + gex, ws disabled)",
                    emoji="🚀",
                )

        done, pending = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_EXCEPTION
        )

        for t in done:
            exc = t.exception()
            if exc:
                try:
                    logger.error(f"worker failure: {exc}", emoji="💥")
                except Exception:
                    pass
                # Do NOT re-raise — convert to controlled shutdown
                break

    except asyncio.CancelledError:
        try:
            logger.info("orchestrator cancelled", emoji="🛑")
        except Exception:
            pass

    except Exception as e:
        try:
            logger.error(f"orchestrator internal error: {e}", emoji="💥")
        except Exception:
            pass
        # Swallow exception to preserve process control

    finally:
        stop_event.set()

        for t in tasks:
            if not t.done():
                t.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)

        try:
            logger.info("orchestrator exiting", emoji="✅")
        except Exception:
            pass