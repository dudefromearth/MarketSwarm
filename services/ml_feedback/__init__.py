# services/ml_feedback/__init__.py
"""ML Feedback Loop for Trade Selector optimization.

This module provides:
- Feature extraction with versioning for point-in-time correctness
- Model training with walk-forward validation
- Two-tier inference (fast + deep paths)
- A/B experiment management
- Circuit breakers for safety

Architecture:
- Trade Selector generates ideas and scores them (rule-based + ML)
- ML Inference adds ml_score blended with original_score
- Decisions logged immutably for reproducibility
- Outcomes tracked via P&L events
- Training pipeline learns from historical outcomes
"""

from .config import MLConfig, FEATURE_SET_VERSION
from .feature_extractor import FeatureExtractor
from .inference_engine import InferenceEngine, FastScoringResult, DeepScoringResult
from .decision_logger import DecisionLogger
from .pnl_ledger import PnLLedger
from .experiment_manager import ExperimentManager
from .circuit_breakers import CircuitBreaker, BreakerStatus

__all__ = [
    'MLConfig',
    'FEATURE_SET_VERSION',
    'FeatureExtractor',
    'InferenceEngine',
    'FastScoringResult',
    'DeepScoringResult',
    'DecisionLogger',
    'PnLLedger',
    'ExperimentManager',
    'CircuitBreaker',
    'BreakerStatus',
]
