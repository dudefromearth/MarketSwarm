# services/ml_feedback/inference_engine.py
"""Two-tier ML inference engine: fast path (sync) + deep path (async)."""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Any, Optional, List
import pickle
import numpy as np

from .config import DEFAULT_CONFIG, MLConfig
from .feature_extractor import (
    FeatureExtractor,
    FeatureVector,
    MarketSnapshot,
    TradeIdea,
)


@dataclass
class FastScoringResult:
    """Result from fast path scoring (<5ms)."""
    idea_id: str
    original_score: float
    ml_score: Optional[float]
    final_score: float
    model_version: Optional[int]
    context_id: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DeepScoringResult:
    """Result from deep path scoring (async)."""
    idea_id: str
    ml_score: float
    confidence: float
    tier_probabilities: List[float]
    model_version: int
    feature_snapshot_id: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CachedModel:
    """Cached model for inference."""
    model_id: int
    version: int
    model: Any  # sklearn model
    feature_list: List[str]
    regime: Optional[str] = None

    def predict_score(self, feature_vector: List[float]) -> float:
        """Predict score from feature vector."""
        probs = self.model.predict_proba([feature_vector])[0]
        return self._probability_to_score(probs)

    def predict_proba(self, feature_vector: List[float]) -> np.ndarray:
        """Predict class probabilities."""
        return self.model.predict_proba([feature_vector])[0]

    def _probability_to_score(self, probs: np.ndarray) -> float:
        """Convert profit tier probabilities to 0-100 score."""
        # Weights: big_loss (-1), small_loss (0), small_win (0.5), big_win (1)
        weights = [-1.0, 0.0, 0.5, 1.0]
        expected_value = sum(p * w for p, w in zip(probs, weights))
        return max(0, min(100, 50 + expected_value * 50))


class InferenceEngine:
    """Two-tier ML scoring: fast path (sync) + deep path (async)."""

    def __init__(self, db=None, config: MLConfig = None, journal_api_url: str = None):
        self.db = db
        self.config = config or DEFAULT_CONFIG
        self.journal_api_url = journal_api_url or "http://localhost:3002"
        self._fast_model: Optional[CachedModel] = None
        self._deep_model: Optional[CachedModel] = None
        self._regime_models: Dict[str, CachedModel] = {}
        self._feature_extractor = FeatureExtractor(config)
        self._context_cache: Dict[str, Dict[str, Any]] = {}
        self._context_timestamps: Dict[str, datetime] = {}

    async def load_models(self) -> None:
        """Load champion models from registry (via API or direct DB)."""
        import logging
        logger = logging.getLogger(__name__)

        # Try API first, then fallback to direct DB
        logger.info(f"[INFERENCE] Loading models from API: {self.journal_api_url}")
        champion = await self._load_champion_model_via_api()
        if champion:
            logger.info(f"[INFERENCE] Loaded champion model v{champion.version} via API")
        elif self.db:
            logger.info("[INFERENCE] API load failed, trying direct DB")
            champion = await self._load_champion_model_from_db()
            if champion:
                logger.info(f"[INFERENCE] Loaded champion model v{champion.version} via DB")
        else:
            logger.warning("[INFERENCE] No champion model loaded (no API response and no DB)")

        if champion:
            self._fast_model = champion
            self._deep_model = champion

        # Load regime-specific models
        for regime in ['chaos', 'goldilocks_1', 'goldilocks_2', 'zombieland']:
            regime_model = await self._load_champion_model_via_api(regime=regime)
            if not regime_model and self.db:
                regime_model = await self._load_champion_model_from_db(regime=regime)
            if regime_model:
                self._regime_models[regime] = regime_model

    async def _load_champion_model_via_api(self, regime: str = None) -> Optional[CachedModel]:
        """Load champion model via Journal API (includes model blob)."""
        import aiohttp
        import json
        import base64

        try:
            url = f"{self.journal_api_url}/api/internal/ml/models/champion?include_blob=true"
            if regime:
                url += f"&regime={regime}"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None

                    data = await resp.json()
                    if not data.get('success') or not data.get('data'):
                        return None

                    model_data = data['data']
                    if not model_data.get('modelBlob'):
                        return None

                    # Decode base64 model blob
                    model_bytes = base64.b64decode(model_data['modelBlob'])
                    model = pickle.loads(model_bytes)

                    return CachedModel(
                        model_id=model_data['id'],
                        version=model_data['modelVersion'],
                        model=model,
                        feature_list=model_data.get('featureList', []),
                        regime=regime,
                    )
        except Exception as e:
            # Silently fail - will try DB fallback
            return None

    async def _load_champion_model_from_db(self, regime: str = None) -> Optional[CachedModel]:
        """Load champion model from database (fallback)."""
        if not self.db:
            return None

        query = """
            SELECT id, model_version, model_blob, feature_list, hyperparameters
            FROM ml_models
            WHERE status = 'champion'
        """
        params = []

        if regime:
            query += " AND JSON_EXTRACT(hyperparameters, '$.regime') = %s"
            params.append(regime)
        else:
            query += " AND (JSON_EXTRACT(hyperparameters, '$.regime') IS NULL OR JSON_EXTRACT(hyperparameters, '$.regime') = 'all')"

        query += " ORDER BY deployed_at DESC LIMIT 1"

        row = await self.db.fetch_one(query, params)
        if not row:
            return None

        import json
        model = pickle.loads(row['model_blob'])
        feature_list = json.loads(row['feature_list'])

        return CachedModel(
            model_id=row['id'],
            version=row['model_version'],
            model=model,
            feature_list=feature_list,
            regime=regime,
        )

    def cache_market_context(
        self,
        context_id: str,
        market_data: MarketSnapshot
    ) -> None:
        """Cache market context (call once per second, not per idea)."""
        self._context_cache[context_id] = self._feature_extractor.extract_market_context(market_data)
        self._context_timestamps[context_id] = datetime.utcnow()
        self._cleanup_old_contexts()

    def _cleanup_old_contexts(self) -> None:
        """Remove expired context cache entries."""
        now = datetime.utcnow()
        ttl_seconds = self.config.context_cache_seconds
        expired = [
            cid for cid, ts in self._context_timestamps.items()
            if (now - ts).total_seconds() > ttl_seconds
        ]
        for cid in expired:
            self._context_cache.pop(cid, None)
            self._context_timestamps.pop(cid, None)

    async def score_idea_fast(
        self,
        idea: TradeIdea,
        market_context_id: str,
        experiment_id: Optional[int] = None,
    ) -> FastScoringResult:
        """Fast path scoring (<5ms). Always runs synchronously."""

        # Get cached market context
        context = self._context_cache.get(market_context_id)
        if not context:
            return self._fallback_to_rules(idea)

        # Get model (regime-specific if available)
        regime = context.get('vix_regime')
        model = self._regime_models.get(regime) or self._fast_model
        if not model:
            return self._fallback_to_rules(idea)

        # Extract strategy-specific features
        strategy_features = self._extract_strategy_features(idea, context)

        # Build feature vector
        feature_vector = self._to_vector(strategy_features, model.feature_list)

        # Score
        ml_score = model.predict_score(feature_vector)

        # Blend scores
        final_score = self._blend_scores(
            idea.score,
            ml_score,
            weight=self.config.ml_weight_conservative
        )

        return FastScoringResult(
            idea_id=idea.id,
            original_score=idea.score,
            ml_score=ml_score,
            final_score=final_score,
            model_version=model.version,
            context_id=market_context_id,
        )

    async def score_idea_deep(
        self,
        idea: TradeIdea,
        market_data: MarketSnapshot,
    ) -> DeepScoringResult:
        """Deep path scoring (async). Updates ranking in background."""

        # Full feature extraction
        features = self._feature_extractor.extract_features(idea, market_data)

        # Get deep model
        model = self._deep_model
        if not model:
            # Return default result if no model
            return DeepScoringResult(
                idea_id=idea.id,
                ml_score=idea.score,
                confidence=0.0,
                tier_probabilities=[0.25, 0.25, 0.25, 0.25],
                model_version=0,
                feature_snapshot_id=0,
            )

        # Build feature vector
        feature_vector = features.to_model_input(model.feature_list)

        # Get probabilities
        probabilities = model.predict_proba(feature_vector)

        # Compute score and confidence
        ml_score = model._probability_to_score(probabilities)
        confidence = self._compute_confidence(probabilities)

        # Store feature snapshot
        feature_snapshot_id = await self._store_features(features)

        return DeepScoringResult(
            idea_id=idea.id,
            ml_score=ml_score,
            confidence=confidence,
            tier_probabilities=probabilities.tolist(),
            model_version=model.version,
            feature_snapshot_id=feature_snapshot_id,
        )

    def _fallback_to_rules(self, idea: TradeIdea) -> FastScoringResult:
        """Graceful degradation when ML unavailable."""
        return FastScoringResult(
            idea_id=idea.id,
            original_score=idea.score,
            ml_score=None,
            final_score=idea.score,
            model_version=None,
            context_id=None,
        )

    def _extract_strategy_features(
        self,
        idea: TradeIdea,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract strategy-specific features (fast path)."""
        spot = context.get('spot_price', 0)
        features = dict(context)

        # Strategy features
        features['strategy_type'] = idea.strategy
        features['side'] = idea.side
        features['dte'] = idea.dte
        features['width'] = idea.width
        features['original_score'] = idea.score

        if spot > 0:
            features['strike_vs_spot'] = (idea.strike - spot) / spot

        return features

    def _to_vector(
        self,
        features: Dict[str, Any],
        feature_list: List[str]
    ) -> List[float]:
        """Convert feature dict to ordered vector."""
        result = []
        for name in feature_list:
            val = features.get(name)
            if val is None:
                result.append(0.0)
            elif isinstance(val, bool):
                result.append(1.0 if val else 0.0)
            elif isinstance(val, str):
                result.append(self._encode_categorical(name, val))
            else:
                result.append(float(val))
        return result

    def _encode_categorical(self, feature: str, value: str) -> float:
        """Encode categorical features as numeric."""
        encodings = {
            'vix_regime': {
                'chaos': 3.0,
                'goldilocks_2': 2.0,
                'goldilocks_1': 1.0,
                'zombieland': 0.0,
            },
            'bias_direction': {
                'bullish': 1.0,
                'neutral': 0.0,
                'bearish': -1.0,
            },
            'strategy_type': {
                'single': 1.0,
                'vertical': 2.0,
                'butterfly': 3.0,
            },
            'side': {
                'call': 1.0,
                'put': -1.0,
            },
        }
        return encodings.get(feature, {}).get(value, 0.0)

    def _blend_scores(
        self,
        original_score: float,
        ml_score: Optional[float],
        weight: float
    ) -> float:
        """Blend rule-based and ML scores."""
        if ml_score is None:
            return original_score
        return original_score * (1 - weight) + ml_score * weight

    def _compute_confidence(self, probabilities: np.ndarray) -> float:
        """Compute confidence from probability distribution."""
        # Higher confidence when one tier dominates
        max_prob = max(probabilities)
        entropy = -sum(p * np.log(p + 1e-10) for p in probabilities)
        max_entropy = np.log(len(probabilities))
        normalized_entropy = entropy / max_entropy

        # Confidence = max_prob weighted by inverse entropy
        return max_prob * (1 - normalized_entropy)

    async def _store_features(self, features: FeatureVector) -> int:
        """Store feature snapshot and return ID."""
        if not self.db:
            return 0

        feature_dict = features.to_dict()
        columns = list(feature_dict.keys())
        values = list(feature_dict.values())

        placeholders = ', '.join(['%s'] * len(values))
        column_names = ', '.join(columns)

        result = await self.db.execute(
            f"INSERT INTO ml_feature_snapshots ({column_names}) VALUES ({placeholders})",
            values
        )
        return result.lastrowid if result else 0

    def get_model_info(self) -> Dict[str, Any]:
        """Get info about loaded models."""
        return {
            'fast_model': {
                'id': self._fast_model.model_id if self._fast_model else None,
                'version': self._fast_model.version if self._fast_model else None,
            },
            'deep_model': {
                'id': self._deep_model.model_id if self._deep_model else None,
                'version': self._deep_model.version if self._deep_model else None,
            },
            'regime_models': {
                regime: {'id': m.model_id, 'version': m.version}
                for regime, m in self._regime_models.items()
            },
            'context_cache_size': len(self._context_cache),
        }
