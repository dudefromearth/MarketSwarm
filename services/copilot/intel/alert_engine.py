# services/copilot/intel/alert_engine.py
"""
Alert Engine - Queue-based alert evaluation system.

Evaluates alerts against real-time market data using pluggable evaluators.
Supports both simple (price, debit) and AI-powered (theta/gamma) alerts.

Pattern follows Commentary subsystem (queue-based processing with subscribers).
"""

import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Callable, Dict, List, Optional

from redis.asyncio import Redis


@dataclass
class AlertEngineConfig:
    """Configuration for the alert engine."""
    enabled: bool = True
    fast_loop_interval_ms: int = 1000   # 1 second for price/debit alerts
    slow_loop_interval_ms: int = 5000   # 5 seconds for AI alerts
    max_queue_size: int = 1000
    # Redis keys - should be set from Truth config
    redis_key_prefix: str = "copilot:alerts"
    publish_channel: str = "copilot:alerts:events"
    latest_key: str = "copilot:alerts:latest"
    # Role gating config
    role_gating: Optional[Dict[str, list]] = None
    limits: Optional[Dict[str, dict]] = None
    max_alerts_per_user: int = 50


@dataclass
class AlertEvaluation:
    """Result of evaluating an alert against market data."""
    alert_id: str
    should_trigger: bool
    confidence: float  # 0.0-1.0
    reasoning: str
    zone_low: Optional[float] = None
    zone_high: Optional[float] = None
    timestamp: float = field(default_factory=time.time)
    provider: Optional[str] = None
    model: Optional[str] = None
    tokens_used: Optional[int] = None
    latency_ms: Optional[float] = None


@dataclass
class Alert:
    """Internal alert representation matching UI types."""
    id: str
    type: str  # price, debit, profit_target, trailing_stop, ai_theta_gamma, etc.
    source: Dict[str, Any]
    condition: str  # above, below, at, outside_zone, inside_zone
    target_value: float
    behavior: str  # remove_on_hit, once_only, repeat
    priority: str  # low, medium, high, critical
    enabled: bool
    triggered: bool
    triggered_at: Optional[float]
    trigger_count: int
    created_at: float
    updated_at: float
    color: str
    label: Optional[str] = None
    was_on_other_side: Optional[bool] = None

    # Type-specific fields
    strategy_id: Optional[str] = None
    entry_debit: Optional[float] = None
    min_profit_threshold: Optional[float] = None
    high_water_mark: Optional[float] = None
    high_water_mark_profit: Optional[float] = None
    zone_low: Optional[float] = None
    zone_high: Optional[float] = None
    is_zone_active: bool = False
    ai_confidence: Optional[float] = None
    ai_reasoning: Optional[str] = None
    last_ai_update: Optional[float] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Alert":
        """Create Alert from dict (snake_case or camelCase)."""
        def get(key: str, default=None):
            # Try snake_case first, then camelCase
            snake = key
            camel = "".join(
                word.capitalize() if i > 0 else word
                for i, word in enumerate(key.split("_"))
            )
            return data.get(snake, data.get(camel, default))

        return cls(
            id=data["id"],
            type=data["type"],
            source=data.get("source", {}),
            condition=get("condition", "above"),
            target_value=float(get("target_value", get("targetValue", 0))),
            behavior=get("behavior", "once_only"),
            priority=get("priority", "medium"),
            enabled=get("enabled", True),
            triggered=get("triggered", False),
            triggered_at=get("triggered_at", get("triggeredAt")),
            trigger_count=int(get("trigger_count", get("triggerCount", 0))),
            created_at=float(get("created_at", get("createdAt", time.time()))),
            updated_at=float(get("updated_at", get("updatedAt", time.time()))),
            color=get("color", "#ffffff"),
            label=get("label"),
            was_on_other_side=get("was_on_other_side", get("wasOnOtherSide")),
            strategy_id=get("strategy_id", get("strategyId")),
            entry_debit=get("entry_debit", get("entryDebit")),
            min_profit_threshold=get("min_profit_threshold", get("minProfitThreshold")),
            high_water_mark=get("high_water_mark", get("highWaterMark")),
            high_water_mark_profit=get("high_water_mark_profit", get("highWaterMarkProfit")),
            zone_low=get("zone_low", get("zoneLow")),
            zone_high=get("zone_high", get("zoneHigh")),
            is_zone_active=get("is_zone_active", get("isZoneActive", False)),
            ai_confidence=get("ai_confidence", get("aiConfidence")),
            ai_reasoning=get("ai_reasoning", get("aiReasoning")),
            last_ai_update=get("last_ai_update", get("lastAIUpdate")),
        )

    def to_dict(self) -> dict:
        """Convert to dict with camelCase keys for JSON/UI compatibility."""
        return {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "condition": self.condition,
            "targetValue": self.target_value,
            "behavior": self.behavior,
            "priority": self.priority,
            "enabled": self.enabled,
            "triggered": self.triggered,
            "triggeredAt": self.triggered_at,
            "triggerCount": self.trigger_count,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "color": self.color,
            "label": self.label,
            "wasOnOtherSide": self.was_on_other_side,
            "strategyId": self.strategy_id,
            "entryDebit": self.entry_debit,
            "minProfitThreshold": self.min_profit_threshold,
            "highWaterMark": self.high_water_mark,
            "highWaterMarkProfit": self.high_water_mark_profit,
            "zoneLow": self.zone_low,
            "zoneHigh": self.zone_high,
            "isZoneActive": self.is_zone_active,
            "aiConfidence": self.ai_confidence,
            "aiReasoning": self.ai_reasoning,
            "lastAIUpdate": self.last_ai_update,
        }


class BaseEvaluator(ABC):
    """Abstract base class for alert evaluators."""

    @property
    @abstractmethod
    def alert_type(self) -> str:
        """Return the alert type this evaluator handles."""
        pass

    @property
    def is_ai_powered(self) -> bool:
        """Whether this evaluator uses AI (slow loop)."""
        return False

    @abstractmethod
    async def evaluate(self, alert: Alert, market_data: dict) -> AlertEvaluation:
        """
        Evaluate an alert against market data.

        Args:
            alert: The alert to evaluate
            market_data: Current market data snapshot

        Returns:
            AlertEvaluation with trigger decision and reasoning
        """
        pass


class AlertEngine:
    """
    Main alert evaluation engine.

    Manages alerts, evaluators, and evaluation loops.
    Uses queue-based processing pattern from Commentary subsystem.
    """

    def __init__(
        self,
        config: AlertEngineConfig,
        redis: Optional[Redis] = None,
        logger=None,
    ):
        self._config = config
        self._redis = redis
        self._logger = logger

        # Evaluator registry
        self._evaluators: Dict[str, BaseEvaluator] = {}

        # Alert cache (id -> Alert)
        self._alerts: Dict[str, Alert] = {}

        # Market data cache
        self._market_data: dict = {}

        # Pending evaluations queue
        self._pending_queue: asyncio.Queue = asyncio.Queue(
            maxsize=config.max_queue_size
        )

        # Subscriber callbacks
        self._subscribers: List[Callable[[AlertEvaluation], None]] = []

        # Processing tasks
        self._fast_loop_task: Optional[asyncio.Task] = None
        self._slow_loop_task: Optional[asyncio.Task] = None
        self._running = False

    def _log(self, msg: str, level: str = "info", emoji: str = ""):
        """Log a message using the logger if available."""
        if self._logger:
            fn = getattr(self._logger, level, self._logger.info)
            if emoji:
                fn(msg, emoji=emoji)
            else:
                fn(msg)
        else:
            print(f"[alert_engine] {msg}")

    def register_evaluator(self, evaluator: BaseEvaluator) -> None:
        """Register an evaluator for an alert type."""
        self._evaluators[evaluator.alert_type] = evaluator
        self._log(f"Registered evaluator: {evaluator.alert_type}", emoji="")

    def get_evaluator(self, alert_type: str) -> Optional[BaseEvaluator]:
        """Get the evaluator for an alert type."""
        return self._evaluators.get(alert_type)

    def subscribe(self, callback: Callable[[AlertEvaluation], None]) -> None:
        """Subscribe to alert evaluation results."""
        self._subscribers.append(callback)

    def _notify_subscribers(self, evaluation: AlertEvaluation) -> None:
        """Notify all subscribers of an evaluation result."""
        for callback in self._subscribers:
            try:
                callback(evaluation)
            except Exception as e:
                self._log(f"Subscriber callback error: {e}", level="warn", emoji="")

    async def load_alerts(self) -> None:
        """Load alerts from Redis."""
        if not self._redis:
            self._log("No Redis connection, skipping alert load", level="warn")
            return

        try:
            # Scan for all alert keys
            prefix = f"{self._config.redis_key_prefix}:"
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor, match=f"{prefix}*", count=100
                )
                for key in keys:
                    # Skip non-alert keys (like alerts:events, alerts:latest)
                    if key.count(":") > 1:
                        continue
                    try:
                        data = await self._redis.get(key)
                        if data:
                            alert_dict = json.loads(data)
                            alert = Alert.from_dict(alert_dict)
                            self._alerts[alert.id] = alert
                    except Exception as e:
                        self._log(f"Error loading alert {key}: {e}", level="warn")

                if cursor == 0:
                    break

            self._log(f"Loaded {len(self._alerts)} alerts from Redis", emoji="")
        except Exception as e:
            self._log(f"Error loading alerts: {e}", level="error", emoji="")

    async def save_alert(self, alert: Alert) -> None:
        """Save an alert to Redis."""
        if not self._redis:
            return

        key = f"{self._config.redis_key_prefix}:{alert.id}"
        await self._redis.set(key, json.dumps(alert.to_dict()), ex=86400 * 30)

    async def delete_alert(self, alert_id: str) -> None:
        """Delete an alert from Redis and cache."""
        if alert_id in self._alerts:
            del self._alerts[alert_id]

        if self._redis:
            key = f"{self._config.redis_key_prefix}:{alert_id}"
            await self._redis.delete(key)

    async def add_alert(self, alert: Alert) -> None:
        """Add or update an alert."""
        self._alerts[alert.id] = alert
        await self.save_alert(alert)
        await self._publish_event("alert_added", {"alert": alert.to_dict()})

    async def update_alert(self, alert_id: str, updates: dict) -> Optional[Alert]:
        """Update an alert with partial data."""
        if alert_id not in self._alerts:
            return None

        alert = self._alerts[alert_id]

        # Apply updates
        for key, value in updates.items():
            snake_key = "".join(
                f"_{c.lower()}" if c.isupper() else c for c in key
            ).lstrip("_")
            if hasattr(alert, snake_key):
                setattr(alert, snake_key, value)

        alert.updated_at = time.time()
        self._alerts[alert_id] = alert
        await self.save_alert(alert)
        await self._publish_event("alert_updated", {"alertId": alert_id, "updates": updates})
        return alert

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get an alert by ID."""
        return self._alerts.get(alert_id)

    def get_alerts(self) -> List[Alert]:
        """Get all alerts."""
        return list(self._alerts.values())

    def get_alerts_by_type(self, alert_type: str) -> List[Alert]:
        """Get alerts of a specific type."""
        return [a for a in self._alerts.values() if a.type == alert_type]

    def get_alerts_by_strategy(self, strategy_id: str) -> List[Alert]:
        """Get alerts for a specific strategy."""
        return [
            a for a in self._alerts.values()
            if a.strategy_id == strategy_id
        ]

    async def update_market_data(self, data: dict) -> None:
        """
        Update market data cache.
        Called by orchestrator when market data updates.
        """
        self._market_data = data

        # Queue enabled alerts for evaluation
        for alert in self._alerts.values():
            if alert.enabled and not alert.triggered:
                try:
                    self._pending_queue.put_nowait(alert.id)
                except asyncio.QueueFull:
                    self._log("Evaluation queue full, dropping alert", level="warn")
                    break

    async def _publish_event(self, event_type: str, data: dict) -> None:
        """Publish an event to Redis pub/sub."""
        if not self._redis:
            return

        try:
            payload = {
                "type": event_type,
                "data": data,
                "ts": datetime.now(UTC).isoformat(),
            }
            await self._redis.publish(
                self._config.publish_channel,
                json.dumps(payload),
            )

            # Also store latest state
            if event_type in ("alert_triggered", "ai_evaluation"):
                await self._redis.set(
                    self._config.latest_key,
                    json.dumps(payload),
                    ex=3600
                )

        except Exception as e:
            self._log(f"Publish error: {e}", level="warn")

    def check_role_permission(self, alert_type: str, user_role: str) -> bool:
        """Check if a user role has permission to use an alert type."""
        if not self._config.role_gating:
            return True  # No gating configured, allow all

        allowed_roles = self._config.role_gating.get(alert_type, [])
        if not allowed_roles:
            return True  # Alert type not gated

        return user_role in allowed_roles

    def get_user_limits(self, user_role: str) -> dict:
        """Get alert limits for a user role."""
        if not self._config.limits:
            return {
                "maxAlerts": self._config.max_alerts_per_user,
                "aiAlertsAllowed": True
            }

        return self._config.limits.get(user_role, {
            "maxAlerts": 5,
            "aiAlertsAllowed": False
        })

    def can_create_alert(self, alert_type: str, user_role: str, current_alert_count: int) -> tuple:
        """
        Check if user can create an alert of the given type.
        Returns (allowed: bool, reason: str)
        """
        # Check role permission for alert type
        if not self.check_role_permission(alert_type, user_role):
            return False, f"Alert type '{alert_type}' requires higher subscription tier"

        # Get user limits
        limits = self.get_user_limits(user_role)

        # Check max alerts
        max_alerts = limits.get("maxAlerts", self._config.max_alerts_per_user)
        if current_alert_count >= max_alerts:
            return False, f"Maximum alerts ({max_alerts}) reached for your tier"

        # Check AI alerts permission
        if alert_type.startswith("ai_") and not limits.get("aiAlertsAllowed", False):
            return False, "AI-powered alerts require premium subscription"

        return True, "OK"

    async def _evaluate_alert(self, alert: Alert) -> Optional[AlertEvaluation]:
        """Evaluate a single alert."""
        evaluator = self.get_evaluator(alert.type)
        if not evaluator:
            self._log(f"No evaluator for alert type: {alert.type}", level="warn")
            return None

        try:
            start_time = time.time()
            evaluation = await evaluator.evaluate(alert, self._market_data)
            evaluation.latency_ms = (time.time() - start_time) * 1000
            return evaluation
        except Exception as e:
            self._log(f"Evaluation error for {alert.id}: {e}", level="error")
            return None

    async def _handle_evaluation(self, alert: Alert, evaluation: AlertEvaluation) -> None:
        """Handle an evaluation result."""
        if not evaluation:
            return

        # Update alert state based on evaluation
        if evaluation.should_trigger:
            alert.triggered = True
            alert.triggered_at = evaluation.timestamp
            alert.trigger_count += 1

            # Handle behavior
            if alert.behavior == "remove_on_hit":
                await self.delete_alert(alert.id)
            elif alert.behavior == "once_only":
                alert.enabled = False
                await self.save_alert(alert)
            else:
                # repeat - reset for next trigger
                alert.triggered = False
                alert.was_on_other_side = False
                await self.save_alert(alert)

            # Publish trigger event
            await self._publish_event("alert_triggered", {
                "alertId": alert.id,
                "triggeredAt": evaluation.timestamp,
                "aiReasoning": evaluation.reasoning,
                "aiConfidence": evaluation.confidence,
            })

        # Update AI fields if present
        if evaluation.zone_low is not None:
            alert.zone_low = evaluation.zone_low
        if evaluation.zone_high is not None:
            alert.zone_high = evaluation.zone_high
        if evaluation.provider:
            alert.ai_confidence = evaluation.confidence
            alert.ai_reasoning = evaluation.reasoning
            alert.last_ai_update = evaluation.timestamp
            alert.is_zone_active = evaluation.zone_low is not None
            await self.save_alert(alert)

            # Publish AI evaluation event
            await self._publish_event("ai_evaluation", {
                "alertId": alert.id,
                "timestamp": evaluation.timestamp,
                "provider": evaluation.provider,
                "model": evaluation.model,
                "shouldTrigger": evaluation.should_trigger,
                "confidence": evaluation.confidence,
                "reasoning": evaluation.reasoning,
                "zoneLow": evaluation.zone_low,
                "zoneHigh": evaluation.zone_high,
                "tokensUsed": evaluation.tokens_used,
                "latencyMs": evaluation.latency_ms,
            })

        # Notify subscribers
        self._notify_subscribers(evaluation)

    async def _fast_loop(self) -> None:
        """
        Fast evaluation loop for simple alerts (price, debit, profit_target, trailing_stop).
        Runs every 1 second.
        """
        interval_sec = self._config.fast_loop_interval_ms / 1000

        while self._running:
            try:
                # Evaluate all non-AI alerts
                for alert in self._alerts.values():
                    if not alert.enabled or alert.triggered:
                        continue

                    evaluator = self.get_evaluator(alert.type)
                    if evaluator and not evaluator.is_ai_powered:
                        evaluation = await self._evaluate_alert(alert)
                        if evaluation:
                            await self._handle_evaluation(alert, evaluation)

            except Exception as e:
                self._log(f"Fast loop error: {e}", level="error")

            await asyncio.sleep(interval_sec)

    async def _slow_loop(self) -> None:
        """
        Slow evaluation loop for AI-powered alerts.
        Runs every 5 seconds.
        """
        interval_sec = self._config.slow_loop_interval_ms / 1000

        while self._running:
            try:
                # Evaluate all AI alerts
                for alert in self._alerts.values():
                    if not alert.enabled or alert.triggered:
                        continue

                    evaluator = self.get_evaluator(alert.type)
                    if evaluator and evaluator.is_ai_powered:
                        evaluation = await self._evaluate_alert(alert)
                        if evaluation:
                            await self._handle_evaluation(alert, evaluation)

            except Exception as e:
                self._log(f"Slow loop error: {e}", level="error")

            await asyncio.sleep(interval_sec)

    async def start(self) -> None:
        """Start the alert engine."""
        if not self._config.enabled:
            self._log("Alert engine disabled by config")
            return

        self._running = True

        # Load alerts from Redis
        await self.load_alerts()

        # Start evaluation loops
        self._fast_loop_task = asyncio.create_task(
            self._fast_loop(), name="alert-fast-loop"
        )
        self._slow_loop_task = asyncio.create_task(
            self._slow_loop(), name="alert-slow-loop"
        )

        self._log("Alert engine started", emoji="")

    async def stop(self) -> None:
        """Stop the alert engine."""
        self._running = False

        # Cancel tasks
        if self._fast_loop_task:
            self._fast_loop_task.cancel()
            try:
                await self._fast_loop_task
            except asyncio.CancelledError:
                pass

        if self._slow_loop_task:
            self._slow_loop_task.cancel()
            try:
                await self._slow_loop_task
            except asyncio.CancelledError:
                pass

        # Save all alerts
        for alert in self._alerts.values():
            await self.save_alert(alert)

        self._log("Alert engine stopped", emoji="")
