# shared/setup_base.py

import os
import json
from typing import Dict, Any
from redis.asyncio import Redis


class SetupBase:
    """
    Base class for all MarketSwarm service setup.

    Responsibilities:
      - Load Truth from Redis
      - Extract component definition
      - Inject declared env vars (truth defaults + shell overrides)
      - Pass through structural (non-env) configuration blocks
    """

    # Structural config blocks that should be preserved verbatim
    STRUCTURAL_KEYS = {
        "heatmap",
        "workflow",
        "domain_keys",
        "epochs",
        # copilot service
        "mel",
        "adi",
        "commentary",
        "alerts",
        # vexy_ai service
        "trading_days",
        "non_trading_days",
        "market_holidays",
        "voice_agents",
        "system_preferences",
        "reflection_dial_behavior",
        "response_format",
        "disruptor_logic",
        "fractal_lens",
        "market_snapshot_schema",
        "capabilities",
        # future extensions:
        # "tiles",
        # "campaigns",
        # "regimes",
    }

    def __init__(self, service_name: str, logger=None):
        self.service_name = service_name
        self.logger = logger

    def log(self, message: str, emoji: str = "ℹ️"):
        if self.logger:
            self.logger.info(message, emoji=emoji)

    async def load_truth(self) -> Dict[str, Any]:
        truth_url = os.getenv("TRUTH_REDIS_URL", "redis://127.0.0.1:6379")
        truth_key = os.getenv("TRUTH_REDIS_KEY", "truth")

        self.log(
            f"loading Truth from Redis (url={truth_url}, key={truth_key})",
            emoji="📥",
        )

        redis = Redis.from_url(truth_url, decode_responses=True)
        raw = await redis.get(truth_key)

        if not raw:
            raise RuntimeError(
                f"[setup:{self.service_name}] Truth key '{truth_key}' not found or empty"
            )

        truth = json.loads(raw)
        self.log("Truth loaded successfully", emoji="📄")
        return truth

    async def load(self) -> Dict[str, Any]:
        truth = await self.load_truth()

        components = truth.get("components", {})
        comp = components.get(self.service_name)

        if not comp:
            raise RuntimeError(
                f"[setup:{self.service_name}] component missing in Truth"
            )

        self.log("parsing component definition", emoji="🔍")

        # --------------------------------------------------
        # Base config (common to all services)
        # --------------------------------------------------
        cfg: Dict[str, Any] = {
            "service_name": self.service_name,
            "meta": comp.get("meta", {}),
            "inputs": comp["access_points"].get("subscribe_to", []),
            "outputs": comp["access_points"].get("publish_to", []),
            "heartbeat": comp.get("heartbeat", {}),
            "models": comp.get("models", {}),
            "buses": truth.get("buses", {}),
            "shared_resources": {},
        }

        # --------------------------------------------------
        # Inject declared env vars (truth defaults + shell overrides)
        # --------------------------------------------------
        env_declared = comp.get("env", {})
        if env_declared:
            overridden = 0
            for key, default_value in env_declared.items():
                value = os.getenv(key, default_value)
                cfg[key] = value
                if os.getenv(key) is not None:
                    overridden += 1

            self.log(
                f"injected {len(env_declared)} env vars into config "
                f"({overridden} overridden by shell)",
                emoji="🔧",
            )

        # --------------------------------------------------
        # Pass through structural configuration blocks
        # --------------------------------------------------
        for key in self.STRUCTURAL_KEYS:
            if key in comp:
                cfg[key] = comp[key]
                self.log(
                    f"loaded structural config '{key}'",
                    emoji="🧩",
                )

        # Allow subclasses to extend config
        await self.extend_config(cfg)

        self.log(f"setup complete for {self.service_name}", emoji="🎉")
        return cfg

    async def extend_config(self, config: Dict[str, Any]):
        """
        Hook for subclasses to extend the config dict.
        Default implementation does nothing.
        """
        pass