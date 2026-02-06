# services/ml_feedback/jobs/backfill_features.py
"""Backfill feature snapshots from tracked_ideas entry context."""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Optional
from pathlib import Path

import aiomysql

logger = logging.getLogger(__name__)

# Feature set version - increment when feature extraction changes
FEATURE_SET_VERSION = "v1.0"
FEATURE_EXTRACTOR_VERSION = "v1.0"


def extract_features_from_tracked_idea(row: dict) -> dict:
    """
    Extract ML features from tracked_idea entry context.

    Maps tracked_ideas columns to ml_feature_snapshots columns.
    """
    # Safe float conversion
    def safe_float(val, default=None):
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    # Safe int conversion
    def safe_int(val, default=None):
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    spot = safe_float(row.get('entry_spot'))
    vix = safe_float(row.get('entry_vix'))
    strike = safe_float(row.get('strike'))

    features = {
        # Price action (limited from entry context)
        'spot_price': spot,
        'spot_5m_return': None,  # Not available in backfill
        'spot_15m_return': None,
        'spot_1h_return': None,
        'spot_1d_return': None,
        'intraday_high': None,
        'intraday_low': None,
        'range_position': None,

        # Volatility
        'vix_level': vix,
        'vix_regime': row.get('entry_regime'),
        'vix_term_slope': None,  # Not available
        'iv_rank_30d': None,
        'iv_percentile_30d': None,

        # GEX structure
        'gex_total': None,
        'gex_call_wall': safe_float(row.get('entry_gex_call_wall')),
        'gex_put_wall': safe_float(row.get('entry_gex_put_wall')),
        'gex_gamma_flip': safe_float(row.get('entry_gex_flip')),

        # Computed GEX features
        'spot_vs_call_wall': None,
        'spot_vs_put_wall': None,
        'spot_vs_gamma_flip': None,

        # Market mode (from regime)
        'market_mode': row.get('entry_regime'),
        'bias_lfi': None,
        'bias_direction': None,

        # Time features
        'minutes_since_open': None,
        'day_of_week': safe_int(row.get('entry_day_of_week')),
        'is_opex_week': None,
        'days_to_monthly_opex': None,

        # Cross-asset (not available in backfill)
        'es_futures_premium': None,
        'tnx_level': None,
        'dxy_level': None,
    }

    # Compute derived features where possible
    if spot and features['gex_call_wall']:
        features['spot_vs_call_wall'] = (features['gex_call_wall'] - spot) / spot
    if spot and features['gex_put_wall']:
        features['spot_vs_put_wall'] = (spot - features['gex_put_wall']) / spot
    if spot and features['gex_gamma_flip']:
        features['spot_vs_gamma_flip'] = (features['gex_gamma_flip'] - spot) / spot

    # Convert entry_hour to minutes_since_open
    entry_hour = safe_float(row.get('entry_hour'))
    if entry_hour is not None:
        # Market opens at 9:30 ET, so 9.5 in decimal hours
        minutes_since_open = int((entry_hour - 9.5) * 60)
        if 0 <= minutes_since_open <= 390:  # Valid market hours
            features['minutes_since_open'] = minutes_since_open

    return features


async def backfill_feature_snapshots(
    db_config: dict,
    batch_size: int = 500,
    dry_run: bool = False,
    limit: Optional[int] = None
) -> dict:
    """
    Backfill ml_feature_snapshots from tracked_ideas entry context.

    Only processes ideas that don't already have a feature snapshot.

    Returns:
        dict with counts: {created: int, skipped: int, errors: int}
    """
    stats = {'created': 0, 'skipped': 0, 'errors': 0}

    pool = await aiomysql.create_pool(**db_config, autocommit=False)

    try:
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # Get tracked_ideas that don't have feature snapshots
                query = """
                    SELECT ti.id, ti.entry_spot, ti.entry_vix, ti.entry_regime,
                           ti.entry_hour, ti.entry_day_of_week,
                           ti.entry_gex_flip, ti.entry_gex_call_wall, ti.entry_gex_put_wall,
                           ti.strike, ti.entry_ts
                    FROM tracked_ideas ti
                    LEFT JOIN ml_feature_snapshots fs ON fs.tracked_idea_id = ti.id
                    WHERE fs.id IS NULL
                    ORDER BY ti.entry_ts DESC
                """
                if limit:
                    query += f" LIMIT {limit}"

                await cur.execute(query)
                rows = await cur.fetchall()

                logger.info(f"Found {len(rows)} ideas without feature snapshots")

                inserts = []
                for row in rows:
                    try:
                        features = extract_features_from_tracked_idea(row)

                        # Parse entry timestamp
                        entry_ts = row.get('entry_ts')
                        if entry_ts:
                            snapshot_time = datetime.fromtimestamp(entry_ts / 1000)
                        else:
                            snapshot_time = datetime.utcnow()

                        inserts.append((
                            row['id'],  # tracked_idea_id
                            snapshot_time,
                            FEATURE_SET_VERSION,
                            FEATURE_EXTRACTOR_VERSION,
                            None,  # gex_calc_version
                            None,  # vix_regime_classifier_version
                            # Price action
                            features['spot_price'],
                            features['spot_5m_return'],
                            features['spot_15m_return'],
                            features['spot_1h_return'],
                            features['spot_1d_return'],
                            features['intraday_high'],
                            features['intraday_low'],
                            features['range_position'],
                            # Volatility
                            features['vix_level'],
                            features['vix_regime'],
                            features['vix_term_slope'],
                            features['iv_rank_30d'],
                            features['iv_percentile_30d'],
                            # GEX
                            features['gex_total'],
                            features['gex_call_wall'],
                            features['gex_put_wall'],
                            features['gex_gamma_flip'],
                            features['spot_vs_call_wall'],
                            features['spot_vs_put_wall'],
                            features['spot_vs_gamma_flip'],
                            # Market mode
                            features['market_mode'],
                            features['bias_lfi'],
                            features['bias_direction'],
                            # Time
                            features['minutes_since_open'],
                            features['day_of_week'],
                            features['is_opex_week'],
                            features['days_to_monthly_opex'],
                            # Cross-asset
                            features['es_futures_premium'],
                            features['tnx_level'],
                            features['dxy_level'],
                        ))

                    except Exception as e:
                        logger.warning(f"Error extracting features for {row['id']}: {e}")
                        stats['errors'] += 1

                if dry_run:
                    logger.info(f"[DRY RUN] Would create {len(inserts)} feature snapshots")
                    stats['skipped'] = len(inserts)
                else:
                    # Batch insert
                    for i in range(0, len(inserts), batch_size):
                        batch = inserts[i:i + batch_size]
                        await cur.executemany("""
                            INSERT INTO ml_feature_snapshots (
                                tracked_idea_id, snapshot_time,
                                feature_set_version, feature_extractor_version,
                                gex_calc_version, vix_regime_classifier_version,
                                spot_price, spot_5m_return, spot_15m_return,
                                spot_1h_return, spot_1d_return,
                                intraday_high, intraday_low, range_position,
                                vix_level, vix_regime, vix_term_slope,
                                iv_rank_30d, iv_percentile_30d,
                                gex_total, gex_call_wall, gex_put_wall, gex_gamma_flip,
                                spot_vs_call_wall, spot_vs_put_wall, spot_vs_gamma_flip,
                                market_mode, bias_lfi, bias_direction,
                                minutes_since_open, day_of_week, is_opex_week, days_to_monthly_opex,
                                es_futures_premium, tnx_level, dxy_level
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s,
                                %s, %s, %s, %s,
                                %s, %s, %s
                            )
                        """, batch)
                        await conn.commit()
                        logger.info(f"Created batch {i // batch_size + 1}: {len(batch)} snapshots")

                    stats['created'] = len(inserts)

                logger.info(f"Feature backfill complete: {stats}")
                return stats

    finally:
        pool.close()
        await pool.wait_closed()


async def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Backfill feature snapshots')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without inserting')
    parser.add_argument('--batch-size', type=int, default=500, help='Batch size for inserts')
    parser.add_argument('--limit', type=int, help='Limit number of ideas to process')
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

    result = await backfill_feature_snapshots(
        db_config,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        limit=args.limit
    )

    print(f"\nResults: {json.dumps(result, indent=2)}")


if __name__ == '__main__':
    asyncio.run(main())
