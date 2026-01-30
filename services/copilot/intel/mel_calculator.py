"""
MEL Base Calculator - Abstract base class for model effectiveness calculators.

Each market model (gamma, volume profile, etc.) has its own calculator that
inherits from this base class and implements the specific effectiveness logic.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from collections import deque
import logging

from .mel_models import (
    MELModelScore,
    ModelState,
    Trend,
    Confidence,
    MELConfig,
)


class MELCalculator(ABC):
    """
    Abstract base class for model effectiveness calculators.

    Each model (gamma, volume profile, liquidity, volatility, session)
    has a calculator that:
    1. Takes market data as input
    2. Measures expected vs observed behavior
    3. Outputs an effectiveness score (0-100)
    """

    def __init__(
        self,
        config: MELConfig,
        logger: Optional[logging.Logger] = None,
        history_window: int = 20,
    ):
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.history_window = history_window

        # Historical scores for trend calculation
        self._score_history: deque = deque(maxlen=history_window)

        # Cache for expensive calculations
        self._cache: Dict[str, Any] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds: int = 5

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the name of the model this calculator handles."""
        pass

    @abstractmethod
    def calculate_effectiveness(self, market_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate the effectiveness score for this model.

        Args:
            market_data: Dictionary containing relevant market data

        Returns:
            Tuple of (effectiveness_score, detail_metrics)
            - effectiveness_score: 0-100
            - detail_metrics: Dict of individual metrics that went into the score
        """
        pass

    def calculate_score(self, market_data: Dict[str, Any]) -> MELModelScore:
        """
        Calculate complete model score with effectiveness, trend, state, and confidence.

        This is the main entry point called by the MEL orchestrator.
        """
        effectiveness, detail = self.calculate_effectiveness(market_data)

        # Record for trend calculation
        self._score_history.append({
            "timestamp": datetime.utcnow(),
            "effectiveness": effectiveness,
        })

        return MELModelScore(
            effectiveness=effectiveness,
            trend=self._calculate_trend(),
            state=self._determine_state(effectiveness),
            confidence=self._determine_confidence(detail, market_data),
            detail=detail,
        )

    def _determine_state(self, effectiveness: float) -> ModelState:
        """Determine model state from effectiveness score."""
        if effectiveness >= self.config.valid_threshold:
            return ModelState.VALID
        elif effectiveness >= self.config.degraded_threshold:
            return ModelState.DEGRADED
        else:
            return ModelState.REVOKED

    def _calculate_trend(self) -> Trend:
        """
        Calculate trend based on recent score history.

        Compares average of recent scores vs older scores.
        """
        if len(self._score_history) < 3:
            return Trend.STABLE

        scores = [s["effectiveness"] for s in self._score_history]

        # Split into recent and older
        midpoint = len(scores) // 2
        recent_avg = sum(scores[midpoint:]) / len(scores[midpoint:])
        older_avg = sum(scores[:midpoint]) / len(scores[:midpoint])

        diff = recent_avg - older_avg

        if diff > 3:  # 3% improvement threshold
            return Trend.IMPROVING
        elif diff < -3:  # 3% degradation threshold
            return Trend.DEGRADING
        else:
            return Trend.STABLE

    def _determine_confidence(
        self,
        detail: Dict[str, Any],
        market_data: Dict[str, Any],
    ) -> Confidence:
        """
        Determine confidence level in the effectiveness score.

        Override in subclasses for model-specific confidence logic.
        """
        # Default implementation based on data completeness
        required_fields = self._get_required_data_fields()
        available_fields = sum(1 for f in required_fields if f in market_data and market_data[f] is not None)

        completeness = available_fields / len(required_fields) if required_fields else 1.0

        if completeness >= 0.9:
            return Confidence.HIGH
        elif completeness >= 0.7:
            return Confidence.MEDIUM
        else:
            return Confidence.LOW

    def _get_required_data_fields(self) -> List[str]:
        """
        Return list of required data fields for this calculator.

        Override in subclasses.
        """
        return []

    def _invalidate_cache(self) -> None:
        """Clear the calculation cache."""
        self._cache = {}
        self._cache_timestamp = None

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if self._cache_timestamp is None:
            return False
        elapsed = (datetime.utcnow() - self._cache_timestamp).total_seconds()
        return elapsed < self._cache_ttl_seconds

    def _set_cache(self, key: str, value: Any) -> None:
        """Set a cache value."""
        self._cache[key] = value
        self._cache_timestamp = datetime.utcnow()

    def _get_cache(self, key: str) -> Optional[Any]:
        """Get a cache value if valid."""
        if self._is_cache_valid() and key in self._cache:
            return self._cache[key]
        return None

    # ========== Utility Methods for Subclasses ==========

    def normalize_score(self, value: float, min_val: float = 0, max_val: float = 100) -> float:
        """Normalize a value to 0-100 range."""
        return max(min_val, min(max_val, value))

    def calculate_rate(self, successes: int, total: int, default: float = 0.0) -> float:
        """Calculate success rate as percentage."""
        if total <= 0:
            return default
        return (successes / total) * 100

    def score_categorical(
        self,
        value: str,
        scoring: Dict[str, float],
        default: float = 50.0,
    ) -> float:
        """Convert categorical value to numeric score."""
        return scoring.get(value, default)

    def weighted_average(self, scores: List[Tuple[float, float]]) -> float:
        """
        Calculate weighted average of scores.

        Args:
            scores: List of (score, weight) tuples

        Returns:
            Weighted average score
        """
        total_weight = sum(weight for _, weight in scores)
        if total_weight <= 0:
            return 0.0
        return sum(score * weight for score, weight in scores) / total_weight


class DummyCalculator(MELCalculator):
    """
    Placeholder calculator that returns neutral scores.

    Used for models that aren't fully implemented yet.
    """

    def __init__(
        self,
        model_name: str,
        config: MELConfig,
        logger: Optional[logging.Logger] = None,
    ):
        super().__init__(config, logger)
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def calculate_effectiveness(self, market_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """Return neutral effectiveness score."""
        return 65.0, {
            "note": f"Placeholder for {self._model_name} calculator",
            "implemented": False,
        }
