import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

import redis


class ReplayWorker:
    """
    ReplayWorker

    Replays previously captured spot / chain / ws data from disk
    and publishes them to the exact same Redis keys used in live mode.

    This worker replaces SpotWorker, ChainWorker, and WsWorker entirely
    when MASSIVE_WS_REPLAY = true.
    """

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger

        # ------------------------------------------------------------
        # Redis (resolved strictly from truth.json buses)
        # ------------------------------------------------------------
        buses = config.get("buses", {})

        market_bus = buses.get("market-redis")
        system_bus = buses.get("system-redis")

        if not market_bus or not system_bus:
            raise RuntimeError(
                "ReplayWorker: required Redis buses missing from truth.json"
            )

        self.market_redis = redis.Redis.from_url(
            market_bus["url"], decode_responses=True
        )
        self.system_redis = redis.Redis.from_url(
            system_bus["url"], decode_responses=True
        )

        # ------------------------------------------------------------
        # Capture / Replay directories
        # ------------------------------------------------------------
        self.chain_dir = Path(config["MASSIVE_WS_CAPTURE_CHAIN_DIR"])
        self.spot_dir = Path(config["MASSIVE_WS_CAPTURE_SPOT_DIR"])
        self.ws_dir = Path(config["MASSIVE_WS_CAPTURE_WS_DIR"])

        if not self.chain_dir.exists():
            raise RuntimeError(f"ReplayWorker: missing {self.chain_dir}")
        if not self.ws_dir.exists():
            raise RuntimeError(f"ReplayWorker: missing {self.ws_dir}")

        if not self.spot_dir.exists():
            self.logger.warning(
                f"ReplayWorker: spot capture dir missing: {self.spot_dir}",
                emoji="⚠️",
            )

        # ------------------------------------------------------------
        # Replay controls
        # ------------------------------------------------------------
        self.replay_speed = float(config.get("MASSIVE_REPLAY_SPEED", 1.0))
        self.replay_session = config.get("MASSIVE_REPLAY_SESSION")

        if self.replay_session:
            self.logger.info(
                f"Replay session override detected: {self.replay_session}",
                emoji="🎯",
            )

        self.logger.info(
            "ReplayWorker initialized "
            f"(redis: market={market_bus['url']}, system={system_bus['url']}; "
            f"dirs: chain={self.chain_dir}, ws={self.ws_dir}, spot={self.spot_dir})",
            emoji="🎞️",
        )

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------

    async def run(self, stop_event: asyncio.Event) -> None:
        self.logger.info("ReplayWorker starting", emoji="🎞️")

        try:
            session = self._select_session()
            events = self._load_events(session)
            await self._replay_events(events, stop_event)

        except asyncio.CancelledError:
            self.logger.info("ReplayWorker cancelled", emoji="🛑")
            raise
        except Exception as e:
            self.logger.error(f"ReplayWorker failed: {e}", emoji="💥")
            raise
        finally:
            self.logger.info("ReplayWorker exiting", emoji="✅")

    # ------------------------------------------------------------------
    # Session selection
    # ------------------------------------------------------------------

    def _select_session(self) -> str:
        """
        Session selection order:
        1) Explicit MASSIVE_REPLAY_SESSION
        2) Auto-discover latest valid date
        """

        # --------------------------------------------------
        # Explicit session override
        # --------------------------------------------------
        if self.replay_session:
            sid = self.replay_session
            date = sid[:8]

            chain_file = self.chain_dir / f"chain_{sid}.jsonl"
            spot_file = self.spot_dir / f"spot_{sid}.jsonl"

            ws_files = sorted(
                self.ws_dir.glob(f"ws_capture_{date}_*.jsonl")
            )

            if not chain_file.exists():
                raise RuntimeError(
                    f"Replay session {sid}: missing chain file {chain_file}"
                )

            if not ws_files:
                raise RuntimeError(
                    f"Replay session {sid}: no ws_capture files for date {date}"
                )

            self.session_files = {
                "chain": [chain_file],
                "ws": ws_files,
                "spot": [spot_file] if spot_file.exists() else [],
            }

            self.logger.info(
                f"Replay session selected (explicit): {sid} "
                f"(chain=1, ws={len(ws_files)}, "
                f"spot={'1' if spot_file.exists() else '0'})",
                emoji="📼",
            )

            return sid

        # --------------------------------------------------
        # Auto-discover latest date
        # --------------------------------------------------
        sessions = {}

        for chain_file in self.chain_dir.glob("chain_*.jsonl"):
            sid = chain_file.stem.replace("chain_", "")
            date = sid[:8]

            ws_files = list(self.ws_dir.glob(f"ws_capture_{date}_*.jsonl"))
            if not ws_files:
                continue

            sessions.setdefault(date, {
                "chain": [],
                "ws": [],
                "spot": [],
            })

            sessions[date]["chain"].append(chain_file)
            sessions[date]["ws"].extend(ws_files)

            spot_file = self.spot_dir / f"spot_{sid}.jsonl"
            if spot_file.exists():
                sessions[date]["spot"].append(spot_file)

        if not sessions:
            raise RuntimeError("No valid replay sessions found")

        session_date = sorted(sessions.keys())[-1]
        files = sessions[session_date]

        self.session_files = files

        self.logger.info(
            f"Replay session selected (auto): {session_date} "
            f"(chain={len(files['chain'])}, "
            f"ws={len(files['ws'])}, "
            f"spot={len(files['spot'])})",
            emoji="📼",
        )

        return session_date

    # ------------------------------------------------------------------
    # Load + merge events
    # ------------------------------------------------------------------

    def _load_events(self, session_id: str) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []

        for f in self.session_files["chain"]:
            events += self._load_stream(f, plane="chain")

        for f in self.session_files["ws"]:
            events += self._load_stream(f, plane="ws")

        for f in self.session_files["spot"]:
            events += self._load_stream(f, plane="spot")

        events.sort(key=lambda e: e["ts"])

        self.logger.info(
            f"Loaded replay events: {len(events)}",
            emoji="📦",
        )

        return events

    def _load_stream(self, path: Path, plane: str) -> List[Dict[str, Any]]:
        stream_events = []

        with path.open() as f:
            for line in f:
                rec = json.loads(line)
                stream_events.append(
                    {
                        "plane": plane,
                        "ts": rec["ts"],
                        "payload": rec,
                    }
                )

        self.logger.info(
            f"Loaded {len(stream_events)} {plane} events",
            emoji="📂",
        )

        return stream_events

    # ------------------------------------------------------------------
    # Replay loop
    # ------------------------------------------------------------------

    async def _replay_events(
        self,
        events: List[Dict[str, Any]],
        stop_event: asyncio.Event,
    ) -> None:
        prev_ts: Optional[float] = None

        for event in events:
            if stop_event.is_set():
                break

            ts = event["ts"]

            if prev_ts is not None:
                delay = (ts - prev_ts) / self.replay_speed
                if delay > 0:
                    await asyncio.sleep(delay)

            self._publish_event(event)
            prev_ts = ts

    # ------------------------------------------------------------------
    # Redis publishing (wire-identical to live)
    # ------------------------------------------------------------------

    def _publish_event(self, event: Dict[str, Any]) -> None:
        plane = event["plane"]
        payload = event["payload"]

        if plane == "spot":
            key = "massive:spot"
        elif plane == "chain":
            key = "massive:chain"
        elif plane == "ws":
            key = "massive:ws"
        else:
            raise RuntimeError(f"Unknown replay plane: {plane}")

        self.market_redis.xadd(
            key,
            {
                "ts": payload["ts"],
                "payload": json.dumps(payload),
            },
        )