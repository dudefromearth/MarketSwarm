"""
Healer Strategies - Implementations of healing actions.

Each strategy knows how to perform a specific healing action.
Strategies are stateless and can be safely retried.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from .models import HealingStrategy


class BaseStrategy(ABC):
    """Base class for healing strategies."""

    strategy_type: HealingStrategy

    def __init__(self, config: Dict[str, Any], logger: Any):
        self.config = config
        self.logger = logger

    @abstractmethod
    async def execute(
        self,
        service_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Execute the healing strategy.

        Args:
            service_name: Name of service to heal
            context: Optional context about the failure

        Returns:
            True if healing succeeded, False otherwise
        """
        pass


class RestartStrategy(BaseStrategy):
    """
    Restart a service.

    Publishes restart command to system bus for the target service
    to pick up and self-restart.
    """

    strategy_type = HealingStrategy.RESTART

    async def execute(
        self,
        service_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Request service restart via system bus."""
        try:
            # Get Redis client for system bus
            import redis
            import json

            buses = self.config.get("buses", {}) or {}
            system_url = buses.get("system-redis", {}).get("url", "redis://127.0.0.1:6379")
            r = redis.Redis.from_url(system_url, decode_responses=True)

            # Publish restart command
            command = {
                "action": "restart",
                "service": service_name,
                "source": "vexy_healer",
                "context": context or {},
            }

            channel = f"{service_name}:commands"
            r.publish(channel, json.dumps(command))

            self.logger.info(
                f"Sent restart command to {service_name}",
                emoji="🔄"
            )

            # Wait for service to restart (check heartbeat)
            await asyncio.sleep(5)

            # Check if service is back
            heartbeat_key = f"{service_name}:heartbeat"
            if r.exists(heartbeat_key):
                self.logger.ok(f"Service {service_name} restarted successfully", emoji="✓")
                return True
            else:
                self.logger.warn(f"Service {service_name} not responding after restart", emoji="⚠️")
                return False

        except Exception as e:
            self.logger.error(f"Restart strategy failed for {service_name}: {e}", emoji="❌")
            return False


class FailoverStrategy(BaseStrategy):
    """
    Failover to a backup instance.

    Updates routing to point to backup service instance.
    """

    strategy_type = HealingStrategy.FAILOVER

    async def execute(
        self,
        service_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Attempt failover to backup instance."""
        try:
            import redis
            import json

            buses = self.config.get("buses", {}) or {}
            system_url = buses.get("system-redis", {}).get("url", "redis://127.0.0.1:6379")
            r = redis.Redis.from_url(system_url, decode_responses=True)

            # Check for backup instance
            backup_key = f"{service_name}:backup:heartbeat"
            if not r.exists(backup_key):
                self.logger.warn(
                    f"No backup instance for {service_name}",
                    emoji="⚠️"
                )
                return False

            # Update routing to use backup
            routing_key = f"routing:{service_name}"
            r.set(routing_key, json.dumps({
                "primary": False,
                "using_backup": True,
                "switched_at": asyncio.get_event_loop().time(),
            }))

            self.logger.ok(
                f"Failover to backup complete for {service_name}",
                emoji="✓"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failover strategy failed for {service_name}: {e}", emoji="❌")
            return False


class EscalateStrategy(BaseStrategy):
    """
    Escalate to human intervention.

    Sends alert to operators and marks service as requiring manual action.
    """

    strategy_type = HealingStrategy.ESCALATE

    async def execute(
        self,
        service_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Escalate to human operators."""
        try:
            import redis
            import json
            from datetime import datetime, UTC

            buses = self.config.get("buses", {}) or {}
            system_url = buses.get("system-redis", {}).get("url", "redis://127.0.0.1:6379")
            r = redis.Redis.from_url(system_url, decode_responses=True)

            # Create escalation record
            escalation = {
                "service": service_name,
                "escalated_at": datetime.now(UTC).isoformat(),
                "context": context or {},
                "status": "pending",
                "requires_human": True,
            }

            # Store escalation
            escalation_key = f"escalations:{service_name}"
            r.set(escalation_key, json.dumps(escalation), ex=86400)  # 24h TTL

            # Publish to alert channel
            r.publish("alerts:critical", json.dumps({
                "type": "service_escalation",
                "service": service_name,
                "message": f"Service {service_name} requires manual intervention",
            }))

            self.logger.warn(
                f"Escalated {service_name} for human intervention",
                emoji="🚨"
            )

            # Escalation always "succeeds" (meaning we successfully escalated)
            return True

        except Exception as e:
            self.logger.error(f"Escalate strategy failed for {service_name}: {e}", emoji="❌")
            return False


class WaitStrategy(BaseStrategy):
    """
    Wait before retrying.

    Sometimes services recover on their own - this strategy
    just waits and checks again.
    """

    strategy_type = HealingStrategy.WAIT

    async def execute(
        self,
        service_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Wait and check if service recovers."""
        try:
            wait_time = self.config.get("healer", {}).get("wait_time_sec", 30)

            self.logger.info(
                f"Waiting {wait_time}s for {service_name} to recover",
                emoji="⏳"
            )

            await asyncio.sleep(wait_time)

            # Check if service is back
            import redis
            buses = self.config.get("buses", {}) or {}
            system_url = buses.get("system-redis", {}).get("url", "redis://127.0.0.1:6379")
            r = redis.Redis.from_url(system_url, decode_responses=True)

            heartbeat_key = f"{service_name}:heartbeat"
            if r.exists(heartbeat_key):
                self.logger.ok(f"Service {service_name} recovered", emoji="✓")
                return True
            else:
                self.logger.warn(f"Service {service_name} still down after wait", emoji="⚠️")
                return False

        except Exception as e:
            self.logger.error(f"Wait strategy failed for {service_name}: {e}", emoji="❌")
            return False


# Strategy registry
STRATEGIES: Dict[HealingStrategy, type] = {
    HealingStrategy.RESTART: RestartStrategy,
    HealingStrategy.FAILOVER: FailoverStrategy,
    HealingStrategy.ESCALATE: EscalateStrategy,
    HealingStrategy.WAIT: WaitStrategy,
}


def get_strategy(
    strategy_type: HealingStrategy,
    config: Dict[str, Any],
    logger: Any,
) -> BaseStrategy:
    """Get a strategy instance by type."""
    strategy_class = STRATEGIES.get(strategy_type)
    if not strategy_class:
        raise ValueError(f"Unknown strategy: {strategy_type}")
    return strategy_class(config, logger)
