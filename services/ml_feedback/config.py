# services/ml_feedback/config.py
"""Configuration for ML Feedback Loop."""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

# Version tracking - increment when feature extraction changes
FEATURE_SET_VERSION = 'v1.0'
FEATURE_EXTRACTOR_VERSION = 'v1.0'
GEX_CALC_VERSION = 'v1.0'
VIX_REGIME_CLASSIFIER_VERSION = 'v1.0'


@dataclass
class MLConfig:
    """Configuration for ML Feedback Loop."""

    # Feature Groups
    feature_groups: Dict[str, List[str]] = field(default_factory=lambda: {
        'price_action': [
            'spot_5m_return', 'spot_15m_return', 'spot_1h_return',
            'spot_1d_return', 'range_position'
        ],
        'volatility': [
            'vix_level', 'vix_regime', 'vix_term_slope',
            'iv_rank_30d', 'iv_percentile_30d'
        ],
        'gex_structure': [
            'gex_total', 'spot_vs_call_wall', 'spot_vs_put_wall',
            'spot_vs_gamma_flip'
        ],
        'market_mode': [
            'market_mode', 'bias_lfi', 'bias_direction'
        ],
        'time': [
            'minutes_since_open', 'day_of_week',
            'is_opex_week', 'days_to_monthly_opex'
        ],
        'strategy': [
            'strategy_type', 'side', 'dte', 'width',
            'strike_vs_spot', 'original_score'
        ]
    })

    # VIX Regime Thresholds
    vix_thresholds: Dict[str, float] = field(default_factory=lambda: {
        'chaos': 32.0,
        'goldilocks_2_lower': 23.0,
        'goldilocks_1_lower': 17.0,
        'zombieland_upper': 17.0,
    })

    # Profit Tier Boundaries (for labeling)
    profit_tier_boundaries: List[float] = field(default_factory=lambda: [
        -0.5,   # Tier 0: big loss (< -50% of risk unit)
        0.0,    # Tier 1: small loss (-50% to 0%)
        1.0,    # Tier 2: small win (0% to 100% of risk unit)
        # Tier 3: big win (> 100% of risk unit)
    ])

    # Inference Configuration
    fast_model_inference_ms: int = 5  # Target latency for fast path
    deep_model_inference_ms: int = 50  # Target latency for deep path
    context_cache_seconds: int = 1  # Market context cache TTL

    # Training Configuration
    min_training_samples: int = 500
    walk_forward_train_weeks: int = 4
    walk_forward_val_weeks: int = 1

    # Model Configuration
    gradient_boost_params: Dict[str, Any] = field(default_factory=lambda: {
        'n_estimators': 100,
        'max_depth': 5,
        'learning_rate': 0.1,
        'subsample': 0.8,
        'min_samples_leaf': 20,
        'random_state': 42,
    })

    # Experiment Configuration
    default_experiment_duration_days: int = 14
    default_traffic_split: float = 0.10  # 10% to challenger
    default_early_stop_threshold: float = 0.01  # p-value
    min_samples_per_arm: int = 100

    # Score Blending
    ml_weight_shadow: float = 0.0  # Shadow mode: ML logged but not used
    ml_weight_conservative: float = 0.10  # Conservative: 10% ML
    ml_weight_moderate: float = 0.30  # Moderate: 30% ML
    ml_weight_aggressive: float = 0.50  # Aggressive: 50% ML

    # Circuit Breaker Configuration
    max_daily_loss: float = 5000.0  # Max daily loss before stopping
    max_drawdown_pct: float = 0.20  # 20% drawdown limit
    max_orders_per_second: float = 10.0  # Rate limit
    slippage_anomaly_threshold: float = 2.0  # Avg slippage threshold
    min_regime_confidence: float = 0.6  # Min confidence to trade


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breakers."""
    max_daily_loss: float = 5000.0
    max_drawdown_pct: float = 0.20
    max_orders_per_second: float = 10.0
    slippage_anomaly_threshold: float = 2.0
    min_regime_confidence: float = 0.6


# Default configuration instance
DEFAULT_CONFIG = MLConfig()
