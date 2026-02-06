# services/ml_feedback/jobs/compute_labels.py
"""Compute profit tier labels for tracked ideas."""

import asyncio
import logging
from typing import Optional
from decimal import Decimal

import aiomysql

logger = logging.getLogger(__name__)


def classify_profit_tier(final_pnl: float, risk_unit: float) -> int:
    """
    Classify outcome into profit tier.

    Tiers:
        0 = big_loss: lost > 50% of risk
        1 = small_loss: lost 0-50% of risk
        2 = small_win: gained 0-100% of risk
        3 = big_win: gained > 100% of risk
    """
    if risk_unit is None or risk_unit <= 0:
        # Fallback: use absolute P&L thresholds
        if final_pnl < -50:
            return 0
        elif final_pnl < 0:
            return 1
        elif final_pnl < 100:
            return 2
        else:
            return 3

    r2r = final_pnl / risk_unit

    if r2r < -0.5:
        return 0  # big_loss
    elif r2r < 0:
        return 1  # small_loss
    elif r2r < 1.0:
        return 2  # small_win
    else:
        return 3  # big_win


def compute_risk_unit(strategy: str, width: int, debit: float) -> float:
    """Compute risk unit based on strategy type."""
    if strategy == 'single':
        return abs(debit) if debit else 100.0
    elif strategy == 'vertical':
        # Max loss = width for verticals
        return (width or 5) * 100
    elif strategy == 'butterfly':
        # Max loss = debit paid
        return abs(debit) if debit else 100.0
    else:
        return abs(debit) if debit else 100.0


async def compute_profit_tier_labels(
    db_config: dict,
    batch_size: int = 500,
    dry_run: bool = False
) -> dict:
    """
    Compute profit_tier labels for all tracked ideas that are missing them.

    Also computes risk_unit if missing.

    Returns:
        dict with counts: {updated: int, skipped: int, errors: int}
    """
    stats = {'updated': 0, 'skipped': 0, 'errors': 0, 'by_tier': {0: 0, 1: 0, 2: 0, 3: 0}}

    pool = await aiomysql.create_pool(**db_config, autocommit=False)

    try:
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # Get ideas missing profit_tier
                await cur.execute("""
                    SELECT id, strategy, width, debit, final_pnl, risk_unit
                    FROM tracked_ideas
                    WHERE profit_tier IS NULL
                    ORDER BY id
                """)
                rows = await cur.fetchall()

                logger.info(f"Found {len(rows)} ideas missing profit_tier labels")

                updates = []
                for row in rows:
                    try:
                        # Compute risk_unit if missing
                        risk_unit = row['risk_unit']
                        if risk_unit is None:
                            risk_unit = compute_risk_unit(
                                row['strategy'],
                                row['width'],
                                float(row['debit']) if row['debit'] else 0
                            )
                        else:
                            risk_unit = float(risk_unit)

                        # Compute profit tier
                        final_pnl = float(row['final_pnl']) if row['final_pnl'] else 0
                        profit_tier = classify_profit_tier(final_pnl, risk_unit)

                        # Compute r2r_achieved if not set
                        r2r_achieved = final_pnl / risk_unit if risk_unit > 0 else 0

                        updates.append((
                            profit_tier,
                            risk_unit,
                            round(r2r_achieved, 4),
                            row['id']
                        ))
                        stats['by_tier'][profit_tier] += 1

                    except Exception as e:
                        logger.warning(f"Error processing {row['id']}: {e}")
                        stats['errors'] += 1

                if dry_run:
                    logger.info(f"[DRY RUN] Would update {len(updates)} ideas")
                    stats['skipped'] = len(updates)
                else:
                    # Batch update
                    for i in range(0, len(updates), batch_size):
                        batch = updates[i:i + batch_size]
                        await cur.executemany("""
                            UPDATE tracked_ideas
                            SET profit_tier = %s,
                                risk_unit = %s,
                                r2r_achieved = %s
                            WHERE id = %s
                        """, batch)
                        await conn.commit()
                        logger.info(f"Updated batch {i // batch_size + 1}: {len(batch)} ideas")

                    stats['updated'] = len(updates)

                logger.info(f"Label computation complete: {stats}")
                return stats

    finally:
        pool.close()
        await pool.wait_closed()


async def main():
    """CLI entry point."""
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description='Compute profit tier labels')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without updating')
    parser.add_argument('--batch-size', type=int, default=500, help='Batch size for updates')
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

    result = await compute_profit_tier_labels(
        db_config,
        batch_size=args.batch_size,
        dry_run=args.dry_run
    )

    print(f"\nResults: {json.dumps(result, indent=2)}")


if __name__ == '__main__':
    asyncio.run(main())
