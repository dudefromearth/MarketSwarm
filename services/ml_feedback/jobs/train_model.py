# services/ml_feedback/jobs/train_model.py
"""Train ML model for Trade Selector with walk-forward validation."""

import asyncio
import json
import logging
import pickle
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import aiomysql
import numpy as np

logger = logging.getLogger(__name__)

# Feature columns to use for training
FEATURE_COLUMNS = [
    # Strategy features (from tracked_ideas)
    'strategy_encoded',  # 0=single, 1=vertical, 2=butterfly
    'side_encoded',      # 0=call, 1=put
    'dte',
    'width',
    'strike_vs_spot',
    'debit_normalized',
    'score_total',

    # Market context (from ml_feature_snapshots or tracked_ideas)
    'vix_level',
    'vix_regime_encoded',  # 0=chaos, 1=goldilocks_1, 2=goldilocks_2, 3=zombieland
    'spot_vs_call_wall',
    'spot_vs_put_wall',
    'spot_vs_gamma_flip',

    # Time features
    'minutes_since_open',
    'day_of_week',
]

# Regime encoding
REGIME_MAP = {
    'chaos': 0,
    'goldilocks_1': 1,
    'goldilocks_2': 2,
    'zombieland': 3,
}

STRATEGY_MAP = {
    'single': 0,
    'vertical': 1,
    'butterfly': 2,
}

SIDE_MAP = {
    'call': 0,
    'put': 1,
}


def prepare_features(row: dict) -> Optional[List[float]]:
    """
    Prepare feature vector from a tracked_idea row.

    Returns None if required features are missing.
    """
    def safe_float(val, default=0.0):
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def safe_int(val, default=0):
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    # Required fields
    spot = safe_float(row.get('entry_spot'))
    if spot <= 0:
        return None

    strike = safe_float(row.get('strike'))
    strategy = row.get('strategy', 'single')
    side = row.get('side', 'call')
    regime = row.get('entry_regime', 'goldilocks_1')

    features = [
        # Strategy features
        STRATEGY_MAP.get(strategy, 0),
        SIDE_MAP.get(side, 0),
        safe_int(row.get('dte'), 0),
        safe_int(row.get('width'), 0),
        (strike - spot) / spot if spot > 0 else 0,  # strike_vs_spot
        safe_float(row.get('debit'), 0) / 100,  # debit_normalized
        safe_float(row.get('score_total'), 50),

        # Market context
        safe_float(row.get('entry_vix'), 15),
        REGIME_MAP.get(regime, 1),
        safe_float(row.get('spot_vs_call_wall'), 0),
        safe_float(row.get('spot_vs_put_wall'), 0),
        safe_float(row.get('spot_vs_gamma_flip'), 0),

        # Time
        safe_int(row.get('minutes_since_open'), 180),  # default to mid-day
        safe_int(row.get('entry_day_of_week'), 2),
    ]

    return features


async def load_training_data(
    db_config: dict,
    min_samples: int = 100,
    max_days: int = 90
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    Load training data from tracked_ideas.

    Returns:
        X: feature matrix
        y: profit_tier labels
        idea_ids: list of idea IDs for tracking
    """
    pool = await aiomysql.create_pool(**db_config, autocommit=True)

    try:
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)

                await cur.execute("""
                    SELECT ti.id, ti.strategy, ti.side, ti.strike, ti.width, ti.dte,
                           ti.debit, ti.score_total, ti.profit_tier,
                           ti.entry_spot, ti.entry_vix, ti.entry_regime,
                           ti.entry_hour, ti.entry_day_of_week,
                           ti.entry_gex_flip, ti.entry_gex_call_wall, ti.entry_gex_put_wall,
                           ti.entry_ts
                    FROM tracked_ideas ti
                    WHERE ti.profit_tier IS NOT NULL
                      AND ti.entry_ts > %s
                    ORDER BY ti.entry_ts ASC
                """, (int(cutoff.timestamp()),))  # entry_ts is in seconds, not milliseconds

                rows = await cur.fetchall()
                logger.info(f"Loaded {len(rows)} labeled ideas")

                if len(rows) < min_samples:
                    raise ValueError(f"Insufficient training data: {len(rows)} < {min_samples}")

                X_list = []
                y_list = []
                idea_ids = []

                for row in rows:
                    # Compute derived features
                    spot = float(row['entry_spot']) if row['entry_spot'] else 0
                    if spot > 0:
                        gex_call = float(row['entry_gex_call_wall']) if row['entry_gex_call_wall'] else None
                        gex_put = float(row['entry_gex_put_wall']) if row['entry_gex_put_wall'] else None
                        gex_flip = float(row['entry_gex_flip']) if row['entry_gex_flip'] else None

                        row['spot_vs_call_wall'] = (gex_call - spot) / spot if gex_call else 0
                        row['spot_vs_put_wall'] = (spot - gex_put) / spot if gex_put else 0
                        row['spot_vs_gamma_flip'] = (gex_flip - spot) / spot if gex_flip else 0

                    # Convert entry_hour to minutes_since_open
                    entry_hour = float(row['entry_hour']) if row['entry_hour'] else None
                    if entry_hour is not None:
                        row['minutes_since_open'] = int((entry_hour - 9.5) * 60)
                    else:
                        row['minutes_since_open'] = None

                    features = prepare_features(row)
                    if features is not None:
                        X_list.append(features)
                        y_list.append(int(row['profit_tier']))
                        idea_ids.append(row['id'])

                logger.info(f"Prepared {len(X_list)} valid feature vectors")

                return np.array(X_list), np.array(y_list), idea_ids

    finally:
        pool.close()
        await pool.wait_closed()


def walk_forward_validation(
    X: np.ndarray,
    y: np.ndarray,
    train_ratio: float = 0.7,
    n_splits: int = 3
) -> List[Dict[str, Any]]:
    """
    Perform walk-forward validation.

    Splits data chronologically and trains on expanding window.
    """
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import accuracy_score, roc_auc_score, precision_score
    from sklearn.calibration import calibration_curve

    n_samples = len(X)
    results = []

    for split_idx in range(n_splits):
        # Expanding window: use first (train_ratio + split_idx * step) for training
        step = (1 - train_ratio) / n_splits
        train_end = int(n_samples * (train_ratio + split_idx * step))
        val_end = int(n_samples * (train_ratio + (split_idx + 1) * step))

        if val_end > n_samples:
            val_end = n_samples

        X_train, y_train = X[:train_end], y[:train_end]
        X_val, y_val = X[train_end:val_end], y[train_end:val_end]

        if len(X_val) < 10:
            continue

        # Train model
        model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            min_samples_leaf=10,
            random_state=42 + split_idx,
        )
        model.fit(X_train, y_train)

        # Predictions
        y_pred = model.predict(X_val)
        y_proba = model.predict_proba(X_val)

        # Metrics
        metrics = {
            'split': split_idx,
            'train_samples': len(X_train),
            'val_samples': len(X_val),
            'accuracy': accuracy_score(y_val, y_pred),
        }

        # AUC (multi-class)
        try:
            metrics['auc'] = roc_auc_score(y_val, y_proba, multi_class='ovr', average='weighted')
        except Exception:
            metrics['auc'] = None

        # Precision for avoiding big losses (tier 0)
        metrics['precision_avoid_big_loss'] = 1 - precision_score(
            y_val, y_pred, labels=[0], average='micro', zero_division=0
        )

        # Top-k utility (average P&L of top 20% by predicted score)
        scores = np.sum(y_proba * np.array([-1, 0, 0.5, 1]), axis=1)
        top_k = int(len(scores) * 0.2)
        top_indices = np.argsort(scores)[-top_k:]
        metrics['top_20_avg_tier'] = np.mean(y_val[top_indices])

        results.append(metrics)
        auc_str = f"{metrics['auc']:.3f}" if metrics['auc'] else 'N/A'
        logger.info(f"Split {split_idx}: acc={metrics['accuracy']:.3f}, auc={auc_str}")

    return results


async def train_and_save_model(
    db_config: dict,
    model_name: str = "trade_selector_v1",
    min_samples: int = 100,
    max_days: int = 90,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Train ML model and save to database.

    Returns:
        dict with training results and model info
    """
    from sklearn.ensemble import GradientBoostingClassifier

    # Load data
    X, y, idea_ids = await load_training_data(db_config, min_samples, max_days)

    logger.info(f"Training data: {len(X)} samples, label distribution: {np.bincount(y)}")

    # Walk-forward validation
    wfv_results = walk_forward_validation(X, y)

    # Aggregate WFV metrics
    avg_metrics = {
        'val_accuracy': np.mean([r['accuracy'] for r in wfv_results]),
        'val_auc': np.mean([r['auc'] for r in wfv_results if r['auc']]),
        'val_top_20_avg_tier': np.mean([r['top_20_avg_tier'] for r in wfv_results]),
    }

    logger.info(f"WFV Results: {avg_metrics}")

    # Train final model on all data
    final_model = GradientBoostingClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.8,
        min_samples_leaf=10,
        random_state=42,
    )
    final_model.fit(X, y)

    # Feature importance
    feature_importance = dict(zip(FEATURE_COLUMNS, final_model.feature_importances_.tolist()))
    logger.info(f"Top features: {sorted(feature_importance.items(), key=lambda x: -x[1])[:5]}")

    result = {
        'model_name': model_name,
        'train_samples': len(X),
        'label_distribution': np.bincount(y).tolist(),
        'wfv_results': wfv_results,
        'avg_metrics': avg_metrics,
        'feature_importance': feature_importance,
    }

    if dry_run:
        logger.info("[DRY RUN] Would save model to database")
        result['saved'] = False
        return result

    # Save to database
    pool = await aiomysql.create_pool(**db_config, autocommit=True)

    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Get next version number
                await cur.execute(
                    "SELECT COALESCE(MAX(model_version), 0) + 1 FROM ml_models WHERE model_name = %s",
                    (model_name,)
                )
                row = await cur.fetchone()
                next_version = row[0]

                # Serialize model
                model_blob = pickle.dumps(final_model)

                # Insert new model
                await cur.execute("""
                    INSERT INTO ml_models (
                        model_name, model_version, model_type,
                        feature_set_version, model_blob, feature_list, hyperparameters,
                        train_auc, val_auc, train_samples, val_samples,
                        status, deployed_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                    )
                """, (
                    model_name,
                    next_version,
                    'GradientBoostingClassifier',
                    'v1.0',  # feature_set_version
                    model_blob,
                    json.dumps(FEATURE_COLUMNS),
                    json.dumps({
                        'n_estimators': 100,
                        'max_depth': 4,
                        'learning_rate': 0.1,
                        'subsample': 0.8,
                        'min_samples_leaf': 10,
                    }),
                    float(avg_metrics['val_auc']),  # train_auc (convert numpy scalar)
                    float(avg_metrics['val_auc']),
                    len(X),
                    sum(r['val_samples'] for r in wfv_results),
                    'champion',  # Deploy as champion
                ))

                model_id = cur.lastrowid

                # Retire previous champion
                await cur.execute("""
                    UPDATE ml_models
                    SET status = 'retired', retired_at = NOW()
                    WHERE model_name = %s AND id != %s AND status = 'champion'
                """, (model_name, model_id))

                logger.info(f"Saved model {model_name} v{next_version} (id={model_id}) as champion")

                result['model_id'] = model_id
                result['model_version'] = next_version
                result['saved'] = True

    finally:
        pool.close()
        await pool.wait_closed()

    return result


async def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Train ML model for Trade Selector')
    parser.add_argument('--dry-run', action='store_true', help='Preview without saving')
    parser.add_argument('--model-name', default='trade_selector_v1', help='Model name')
    parser.add_argument('--min-samples', type=int, default=100, help='Minimum training samples')
    parser.add_argument('--max-days', type=int, default=90, help='Max days of data to use')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Load database config from truth.json
    truth_path = Path(__file__).parent.parent.parent.parent / 'scripts' / 'truth.json'
    if truth_path.exists():
        truth = json.loads(truth_path.read_text())
        db_cfg = truth.get('services', {}).get('journal', {}).get('db', {})
    else:
        db_cfg = {}

    db_config = {
        'host': db_cfg.get('host', 'localhost'),
        'port': db_cfg.get('port', 3306),
        'user': db_cfg.get('user', 'root'),
        'password': db_cfg.get('password', ''),
        'db': db_cfg.get('database', 'fotw_app'),
    }

    result = await train_and_save_model(
        db_config,
        model_name=args.model_name,
        min_samples=args.min_samples,
        max_days=args.max_days,
        dry_run=args.dry_run
    )

    print(f"\nResults: {json.dumps(result, indent=2, default=str)}")


if __name__ == '__main__':
    asyncio.run(main())
