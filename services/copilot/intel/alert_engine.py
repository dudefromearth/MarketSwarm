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

import aiohttp
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
    analytics_key: str = "copilot:alerts:analytics"
    # Sync channel from Journal service
    sync_channel: str = "alerts:sync"
    # Prompt alerts sync channel
    prompt_alerts_sync_channel: str = "prompt_alerts:sync"
    # Role gating config
    role_gating: Optional[Dict[str, list]] = None
    limits: Optional[Dict[str, dict]] = None
    max_alerts_per_user: int = 50
    # Journal service URL for fetching alerts from database
    journal_api_url: str = "http://localhost:3002"


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
    """Internal alert representation matching database model."""
    id: str
    user_id: int
    type: str  # price, debit, profit_target, trailing_stop, ai_theta_gamma, etc.
    intent_class: str  # informational, reflective, protective
    condition: str  # above, below, at, outside_zone, inside_zone
    target_value: float
    behavior: str  # remove_on_hit, once_only, repeat
    priority: str  # low, medium, high, critical
    source_type: str  # strategy, symbol, portfolio
    source_id: str
    enabled: bool
    triggered: bool
    triggered_at: Optional[str]
    trigger_count: int
    created_at: str
    updated_at: str
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

    # Legacy compatibility - construct source dict from source_type/source_id
    @property
    def source(self) -> Dict[str, Any]:
        return {"type": self.source_type, "id": self.source_id}

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

        # Handle source field - can be dict (legacy) or separate fields (new)
        source = data.get("source", {})
        source_type = get("source_type", get("sourceType", source.get("type", "symbol")))
        source_id = get("source_id", get("sourceId", source.get("id", "")))

        return cls(
            id=data["id"],
            user_id=int(get("user_id", get("userId", 0))),
            type=data["type"],
            intent_class=get("intent_class", get("intentClass", "informational")),
            condition=get("condition", "above"),
            target_value=float(get("target_value", get("targetValue", 0)) or 0),
            behavior=get("behavior", "once_only"),
            priority=get("priority", "medium"),
            source_type=source_type,
            source_id=source_id,
            enabled=get("enabled", True),
            triggered=get("triggered", False),
            triggered_at=get("triggered_at", get("triggeredAt")),
            trigger_count=int(get("trigger_count", get("triggerCount", 0))),
            created_at=get("created_at", get("createdAt", "")),
            updated_at=get("updated_at", get("updatedAt", "")),
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
            "userId": self.user_id,
            "type": self.type,
            "intentClass": self.intent_class,
            "source": self.source,
            "sourceType": self.source_type,
            "sourceId": self.source_id,
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
        intel_redis: Optional[Redis] = None,
        logger=None,
    ):
        self._config = config
        self._redis = redis
        self._intel_redis = intel_redis  # For analytics publishing
        self._logger = logger

        # Evaluator registry
        self._evaluators: Dict[str, BaseEvaluator] = {}

        # Alert cache (id -> Alert)
        self._alerts: Dict[str, Alert] = {}

        # Prompt alert cache (id -> prompt alert dict with reference state)
        self._prompt_alerts: Dict[str, dict] = {}

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
        self._sync_task: Optional[asyncio.Task] = None
        self._running = False

        # Analytics tracking (key from config)
        self._analytics = {
            "alerts_loaded": 0,
            "alerts_evaluated": 0,
            "alerts_triggered": 0,
            "fast_loop_runs": 0,
            "slow_loop_runs": 0,
            "sync_messages": 0,
            "errors": 0,
            "last_evaluation_ms": 0,
            "last_trigger_ts": None,
            "started_at": None,
        }

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

    async def _record_analytics(self, **kwargs) -> None:
        """Record analytics metrics to intel-redis."""
        redis = self._intel_redis or self._redis
        if not redis:
            return
        try:
            analytics_key = self._config.analytics_key
            for key, value in kwargs.items():
                if key.startswith("incr_"):
                    field = key[5:]  # Remove "incr_" prefix
                    self._analytics[field] = self._analytics.get(field, 0) + value
                    await redis.hincrby(analytics_key, field, value)
                else:
                    self._analytics[key] = value
                    await redis.hset(analytics_key, key, str(value) if value is not None else "")
        except Exception as e:
            self._log(f"Analytics error: {e}", level="warn")

    def get_analytics(self) -> dict:
        """Get current analytics snapshot."""
        return {
            **self._analytics,
            "alerts_active": len(self._alerts),
            "evaluators_registered": len(self._evaluators),
            "running": self._running,
        }

    async def get_analytics_from_redis(self) -> dict:
        """Get analytics from intel-redis (includes historical data)."""
        redis = self._intel_redis or self._redis
        if not redis:
            return self.get_analytics()
        try:
            data = await redis.hgetall(self._config.analytics_key)
            return {
                **{k: int(v) if v.isdigit() else v for k, v in data.items()},
                "alerts_active": len(self._alerts),
                "evaluators_registered": len(self._evaluators),
                "running": self._running,
            }
        except Exception:
            return self.get_analytics()

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
        """Load alerts from Journal service database."""
        try:
            await self._load_alerts_from_db()
        except Exception as e:
            self._log(f"Error loading alerts from DB, falling back to Redis: {e}", level="warn")
            await self._load_alerts_from_redis()

    async def _load_alerts_from_db(self) -> None:
        """Load all enabled alerts from Journal service database via internal API."""
        url = f"{self._config.journal_api_url}/api/internal/alerts"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("success") and result.get("data"):
                            self._alerts.clear()
                            for alert_dict in result["data"]:
                                try:
                                    alert = Alert.from_dict(alert_dict)
                                    self._alerts[alert.id] = alert
                                except Exception as e:
                                    self._log(f"Error parsing alert: {e}", level="warn")
                            self._log(f"Loaded {len(self._alerts)} alerts from Journal DB", emoji="")
                            await self._record_analytics(alerts_loaded=len(self._alerts))
                    else:
                        raise Exception(f"HTTP {resp.status}")
        except Exception as e:
            raise Exception(f"Failed to load from Journal API: {e}")

    async def _load_alerts_from_redis(self) -> None:
        """Fallback: Load alerts from Redis cache."""
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
            self._log(f"Error loading alerts from Redis: {e}", level="error", emoji="")

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

            # Record trigger analytics
            await self._record_analytics(
                incr_alerts_triggered=1,
                last_trigger_ts=evaluation.timestamp,
                last_evaluation_ms=int(evaluation.latency_ms)
            )

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
            evaluated_count = 0
            try:
                # Evaluate all non-AI alerts
                for alert in self._alerts.values():
                    if not alert.enabled or alert.triggered:
                        continue

                    evaluator = self.get_evaluator(alert.type)
                    if evaluator and not evaluator.is_ai_powered:
                        evaluation = await self._evaluate_alert(alert)
                        evaluated_count += 1
                        if evaluation:
                            await self._handle_evaluation(alert, evaluation)

                await self._record_analytics(
                    incr_fast_loop_runs=1,
                    incr_alerts_evaluated=evaluated_count
                )
            except Exception as e:
                self._log(f"Fast loop error: {e}", level="error")
                await self._record_analytics(incr_errors=1)

            await asyncio.sleep(interval_sec)

    async def _slow_loop(self) -> None:
        """
        Slow evaluation loop for AI-powered alerts and prompt alerts.
        Runs every 5 seconds.
        """
        interval_sec = self._config.slow_loop_interval_ms / 1000

        while self._running:
            evaluated_count = 0
            try:
                # Evaluate all AI alerts
                for alert in self._alerts.values():
                    if not alert.enabled or alert.triggered:
                        continue

                    evaluator = self.get_evaluator(alert.type)
                    if evaluator and evaluator.is_ai_powered:
                        evaluation = await self._evaluate_alert(alert)
                        evaluated_count += 1
                        if evaluation:
                            await self._handle_evaluation(alert, evaluation)

                # Evaluate prompt alerts
                prompt_evaluator = self.get_evaluator("prompt_driven")
                if prompt_evaluator:
                    for prompt_alert in self._prompt_alerts.values():
                        if prompt_alert.get("lifecycleState") != "active":
                            continue

                        try:
                            # Build market data with reference state
                            market_data_with_ref = {
                                **self._market_data,
                                "reference_states": {
                                    prompt_alert["id"]: prompt_alert.get("referenceState", {})
                                },
                                "strategies": self._market_data.get("strategies", {}),
                            }

                            evaluation = await prompt_evaluator.evaluate(
                                prompt_alert,
                                market_data_with_ref
                            )
                            evaluated_count += 1

                            # Handle prompt alert stage transitions
                            if evaluation.should_trigger:
                                await self._handle_prompt_evaluation(prompt_alert, evaluation)

                        except Exception as e:
                            self._log(f"Prompt alert evaluation error: {e}", level="warn")

                await self._record_analytics(
                    incr_slow_loop_runs=1,
                    incr_alerts_evaluated=evaluated_count
                )
            except Exception as e:
                self._log(f"Slow loop error: {e}", level="error")
                await self._record_analytics(incr_errors=1)

            await asyncio.sleep(interval_sec)

    async def _handle_prompt_evaluation(self, prompt_alert: dict, evaluation) -> None:
        """Handle a prompt alert evaluation result."""
        # Publish stage change event
        await self.publish_prompt_stage_change(
            alert_id=prompt_alert["id"],
            stage=evaluation.reasoning[:50] if hasattr(evaluation, 'reasoning') else "stage_change",
            reasoning=evaluation.reasoning if hasattr(evaluation, 'reasoning') else "",
            confidence=evaluation.confidence if hasattr(evaluation, 'confidence') else 0.5,
        )

        # Update the local cache
        if prompt_alert["id"] in self._prompt_alerts:
            self._prompt_alerts[prompt_alert["id"]]["lastAiConfidence"] = evaluation.confidence
            self._prompt_alerts[prompt_alert["id"]]["lastAiReasoning"] = evaluation.reasoning

    async def _sync_subscription_loop(self) -> None:
        """
        Subscribe to alerts:sync and prompt_alerts:sync Redis channels for real-time updates.
        When Journal service creates/updates/deletes alerts, it publishes to these channels.
        """
        if not self._redis:
            self._log("No Redis connection, skipping sync subscription", level="warn")
            return

        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(
                self._config.sync_channel,
                self._config.prompt_alerts_sync_channel
            )
            self._log(f"Subscribed to {self._config.sync_channel} and {self._config.prompt_alerts_sync_channel}", emoji="")

            while self._running:
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0
                    )
                    if message and message["type"] == "message":
                        data = json.loads(message["data"])
                        action = data.get("action")
                        alert_id = data.get("alert_id")
                        channel = message.get("channel", "")

                        self._log(f"Sync ({channel}): {action} {alert_id}", emoji="")
                        await self._record_analytics(incr_sync_messages=1)

                        # Reload alerts based on channel
                        if channel == self._config.prompt_alerts_sync_channel:
                            await self.load_prompt_alerts()
                        else:
                            await self.load_alerts()

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    self._log(f"Sync subscription error: {e}", level="warn")
                    await asyncio.sleep(1)

        except Exception as e:
            self._log(f"Failed to subscribe to sync channel: {e}", level="error")
        finally:
            try:
                await pubsub.unsubscribe(
                    self._config.sync_channel,
                    self._config.prompt_alerts_sync_channel
                )
            except Exception:
                pass

    async def load_prompt_alerts(self) -> None:
        """Load active prompt alerts from Journal service."""
        url = f"{self._config.journal_api_url}/api/internal/prompt-alerts"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("success") and result.get("data"):
                            self._prompt_alerts.clear()
                            for alert_dict in result["data"]:
                                try:
                                    self._prompt_alerts[alert_dict["id"]] = alert_dict
                                except Exception as e:
                                    self._log(f"Error loading prompt alert: {e}", level="warn")
                            self._log(f"Loaded {len(self._prompt_alerts)} prompt alerts from Journal DB", emoji="")
                    else:
                        self._log(f"Failed to load prompt alerts: HTTP {resp.status}", level="warn")
        except Exception as e:
            self._log(f"Error loading prompt alerts: {e}", level="warn")

    def get_prompt_alerts(self) -> List[dict]:
        """Get all prompt alerts."""
        return list(self._prompt_alerts.values())

    async def publish_prompt_stage_change(
        self,
        alert_id: str,
        stage: str,
        reasoning: str,
        confidence: float
    ) -> None:
        """Publish a prompt alert stage change event."""
        await self._publish_event("prompt_alert_stage_change", {
            "alertId": alert_id,
            "stage": stage,
            "reasoning": reasoning,
            "confidence": confidence,
            "timestamp": datetime.now(UTC).isoformat(),
        })

    async def start(self) -> None:
        """Start the alert engine."""
        if not self._config.enabled:
            self._log("Alert engine disabled by config")
            return

        self._running = True

        # Record start time
        from datetime import datetime
        await self._record_analytics(started_at=datetime.utcnow().isoformat())

        # Load alerts from database
        await self.load_alerts()
        await self.load_prompt_alerts()

        # Start evaluation loops
        self._fast_loop_task = asyncio.create_task(
            self._fast_loop(), name="alert-fast-loop"
        )
        self._slow_loop_task = asyncio.create_task(
            self._slow_loop(), name="alert-slow-loop"
        )

        # Start sync subscription for real-time updates from Journal service
        self._sync_task = asyncio.create_task(
            self._sync_subscription_loop(), name="alert-sync-subscription"
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

        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        # Save all alerts to Redis cache
        for alert in self._alerts.values():
            await self.save_alert(alert)

        self._log("Alert engine stopped", emoji="")
