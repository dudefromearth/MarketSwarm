# services/massive/intel/orchestrator.py

import asyncio
from typing import Dict, Any

from .workers.spot_worker import SpotWorker
from .workers.chain_worker import ChainWorker
from .workers.snapshot_worker import SnapshotWorker
from .workers.ws_worker import WsWorker
from .workers.ws_consumer import WsConsumer
from .workers.ws_hydrator import WsHydrator
from .model_builders.builder import Builder
from .model_builders.model_publisher import ModelPublisher
from .model_builders.gex import GexModelBuilder
from .model_builders.bias_lfi import BiasLfiModelBuilder
from .volume_profile.vp_worker import VolumeProfileWorker


async def run(config: Dict[str, Any], logger) -> None:
    """
    Orchestrator — wiring and lifecycle control for Massive service.

    Pipeline:
    - Spot (provides spot prices)
    - Chain (geometry authority, populates WS subscriptions)
    - Snapshot (chain-only snapshots → Builder)
    - Builder (calculates tiles/deltas)
    - ModelPublisher (publishes live + replay models)
    - GEX (calculates gamma exposure)
    - WsWorker (streams real-time 0-DTE ticks)
    - WsConsumer (reads stream at 2-5 Hz → Hydrator → Builder)
    """
    stop_event = asyncio.Event()
    tasks = []

    logger.info(
        "orchestrator starting (spot + chain + snapshot + builder + model + gex + bias_lfi + ws + vp)",
        emoji="🚀",
    )

    try:
        # 1. SpotWorker (provides spot prices for Chain range calculation)
        spot = SpotWorker(config, logger)
        tasks.append(
            asyncio.create_task(spot.run(stop_event), name="massive-spot")
        )

        # 2. ChainWorker (geometry authority, diff + trigger)
        chain = ChainWorker(config, logger)
        tasks.append(
            asyncio.create_task(chain.run(stop_event), name="massive-chain")
        )

        # 3. Snapshot Worker (chain-only snapshots)
        snapshot = SnapshotWorker(config, logger)
        tasks.append(
            asyncio.create_task(snapshot.run(stop_event), name="massive-snapshot")
        )

        # 4. Builder Worker (calculates tiles/deltas)
        builder = Builder(config, logger)
        tasks.append(
            asyncio.create_task(builder.run(stop_event), name="massive-builder")
        )

        # 5. ModelPublisher Worker (publishes live + replay models)
        model_pub = ModelPublisher(config, logger)
        tasks.append(
            asyncio.create_task(model_pub.run(stop_event), name="massive-model")
        )

        # 6. GEX Model Builder (calculates gamma exposure per strike)
        gex = GexModelBuilder(config, logger)
        tasks.append(
            asyncio.create_task(gex.run(stop_event), name="massive-gex")
        )

        # 7. Bias/LFI Model Builder (calculates directional strength and LFI from GEX)
        bias_lfi = BiasLfiModelBuilder(config, logger)
        tasks.append(
            asyncio.create_task(bias_lfi.run(stop_event), name="massive-bias-lfi")
        )

        # 8. WsWorker (streams real-time ticks to Redis stream)
        ws_worker = WsWorker(config, logger)
        tasks.append(
            asyncio.create_task(ws_worker.run(stop_event), name="massive-ws")
        )

        # 9. WsHydrator (maintains in-memory price state from WS ticks)
        hydrator = WsHydrator(config, logger)

        # 10. WsConsumer (reads stream, drives hydrator, triggers builder at 2-5 Hz)
        ws_consumer = WsConsumer(config, logger)
        tasks.append(
            asyncio.create_task(ws_consumer.run(stop_event), name="massive-ws-consumer")
        )

        # 11. VolumeProfileWorker (real-time SPY volume → SPX profile)
        vp_worker = VolumeProfileWorker(config, logger)
        tasks.append(
            asyncio.create_task(vp_worker.run(stop_event), name="massive-volume-profile")
        )

        # Wire direct injection: snapshot → builder → model_publisher
        snapshot.set_builder(builder)
        builder.set_model_publisher(model_pub)

        # Wire WS path: ws_consumer → hydrator → builder → model_publisher
        ws_consumer.set_hydrator(hydrator)
        ws_consumer.set_builder(builder)

        # Wait for any task to raise exception (or cancellation)
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
                break  # controlled shutdown

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