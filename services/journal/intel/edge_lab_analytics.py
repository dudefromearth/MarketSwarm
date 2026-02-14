# services/journal/intel/edge_lab_analytics.py
"""Edge Lab analytics engine — structural edge analysis, regime correlation,
bias overlay, and edge score computation.

All output is observational. No optimization language. No behavioral recommendations.
Data is presented; interpretation is the user's. Edge Lab is a mirror, not a coach.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict

from .models_v2 import EdgeLabEdgeScore, EdgeLabMetric


class EdgeLabAnalytics:
    """Analytics engine for Edge Lab retrospective trade analysis."""

    # Minimum sample size for meaningful analytics
    MIN_SAMPLE_SIZE = 10

    def __init__(self, db):
        """Initialize with a JournalDBv2 instance."""
        self.db = db

    def suggest_outcome_type(self, setup_id: str, user_id: int) -> Dict[str, Any]:
        """Suggest an outcome type based on setup, hypothesis, and trade data.

        Returns {suggestion, confidence, reasoning}. User always has final say.
        Confidence and reasoning are stored on the outcome for future drift analysis.
        """
        setup = self.db.get_edge_lab_setup(setup_id, user_id)
        if not setup:
            return {'suggestion': None, 'confidence': 0.0, 'reasoning': 'Setup not found'}

        hypothesis = self.db.get_hypothesis_for_setup(setup_id, user_id)

        # Gather signals for heuristic classification
        signals = {
            'has_hypothesis': hypothesis is not None,
            'hypothesis_locked': hypothesis.is_locked if hypothesis else False,
            'entry_defined': bool(setup.entry_defined),
            'exit_defined': bool(setup.exit_defined),
            'has_bias_state': setup.bias_state_json is not None,
        }

        # Read readiness data for bias interference detection
        readiness = self.db.get_readiness_for_date(user_id, setup.setup_date)
        if readiness:
            signals['high_friction'] = readiness.get('friction', '') in ('high', 'extreme')
            signals['poor_sleep'] = readiness.get('sleep', '') in ('poor', 'terrible')
            signals['low_focus'] = readiness.get('focus', '') in ('low', 'very_low')
        else:
            signals['high_friction'] = False
            signals['poor_sleep'] = False
            signals['low_focus'] = False

        # Heuristic rules (order matters — most specific first)
        bias_flags = sum([signals['high_friction'], signals['poor_sleep'], signals['low_focus']])

        if bias_flags >= 2:
            return {
                'suggestion': 'bias_interference',
                'confidence': 0.65,
                'reasoning': 'Multiple readiness indicators suggest elevated bias state at time of trade.',
            }

        if not signals['entry_defined'] or not signals['exit_defined']:
            return {
                'suggestion': 'execution_error',
                'confidence': 0.55,
                'reasoning': 'Entry or exit criteria were not defined prior to trade.',
            }

        if not signals['has_hypothesis'] or not signals['hypothesis_locked']:
            return {
                'suggestion': 'execution_error',
                'confidence': 0.50,
                'reasoning': 'Hypothesis was not locked before trade entry.',
            }

        # Default: structural outcome (cannot determine win/loss without PnL context,
        # and we deliberately do not use PnL in classification)
        return {
            'suggestion': 'structural_win',
            'confidence': 0.40,
            'reasoning': 'Structure was defined with locked hypothesis and clear entry/exit. '
                         'Classification depends on whether the thesis resolved structurally.',
        }

    def compute_regime_correlation(self, user_id: int, start_date: str,
                                    end_date: str) -> Dict[str, Any]:
        """Compute structural validity rate grouped by regime dimensions.

        JOINs setups+outcomes, groups by regime/gex/vol/time_structure/heatmap.
        Buckets below MIN_SAMPLE_SIZE return raw counts with insufficient_sample flag.
        """
        rows = self.db.get_setups_with_outcomes(user_id, start_date, end_date)

        dimensions = ['regime', 'gex_posture', 'vol_state', 'time_structure', 'heatmap_color']
        result = {}

        for dim in dimensions:
            buckets = defaultdict(lambda: {'total': 0, 'structural_wins': 0})
            for row in rows:
                key = row.get(dim, 'unknown')
                buckets[key]['total'] += 1
                if row.get('outcome_type') == 'structural_win':
                    buckets[key]['structural_wins'] += 1

            dim_result = {}
            for key, counts in buckets.items():
                total = counts['total']
                wins = counts['structural_wins']
                if total < self.MIN_SAMPLE_SIZE:
                    dim_result[key] = {
                        'structural_validity_rate': None,
                        'sample_size': total,
                        'structural_wins': wins,
                        'insufficient_sample': True,
                    }
                else:
                    dim_result[key] = {
                        'structural_validity_rate': round(wins / total, 3),
                        'sample_size': total,
                        'structural_wins': wins,
                        'insufficient_sample': False,
                    }
            result[dim] = dim_result

        return {
            'dimensions': result,
            'total_records': len(rows),
            'date_range': {'start': start_date, 'end': end_date},
        }

    def compute_bias_overlay(self, user_id: int, start_date: str,
                              end_date: str) -> Dict[str, Any]:
        """Compute outcome distributions segmented by readiness state.

        JOINs setups+outcomes with user_readiness_log on (user_id, setup_date).
        Output is purely observational data. No suggested behavior changes,
        no optimization language, no 'you should trade when...' framing.
        """
        rows = self.db.get_setups_with_outcomes(user_id, start_date, end_date)

        readiness_dims = ['sleep', 'focus', 'distractions', 'body_state', 'friction']
        result = {}

        for dim in readiness_dims:
            buckets = defaultdict(lambda: defaultdict(int))
            for row in rows:
                # Parse bias state if available
                import json
                bias_json = row.get('bias_state_json')
                if not bias_json:
                    continue
                try:
                    bias = json.loads(bias_json) if isinstance(bias_json, str) else bias_json
                except (json.JSONDecodeError, TypeError):
                    continue

                key = bias.get(dim, 'unknown')
                if not key:
                    key = 'unknown'
                outcome_type = row.get('outcome_type', 'unknown')
                buckets[key][outcome_type] += 1
                buckets[key]['_total'] += 1

            dim_result = {}
            for key, outcomes in buckets.items():
                total = outcomes.pop('_total', 0)
                dim_result[key] = {
                    'outcomes': dict(outcomes),
                    'sample_size': total,
                    'insufficient_sample': total < self.MIN_SAMPLE_SIZE,
                }
            result[dim] = dim_result

        return {
            'dimensions': result,
            'total_records': len(rows),
            'date_range': {'start': start_date, 'end': end_date},
        }

    def compute_edge_score(self, user_id: int, start_date: str, end_date: str,
                            scope: str = 'all') -> Dict[str, Any]:
        """Compute edge score from confirmed outcomes in window.

        Formula: SI*0.35 + ED*0.30 - BI*0.15 + RA*0.20

        PnL is NEVER used in this formula. Edge Score measures process quality,
        not profitability. This is a deliberate design constraint.

        Returns {status: 'insufficient_sample', sample_size} if total < 10.
        """
        rows = self.db.get_setups_with_outcomes(user_id, start_date, end_date)
        total = len(rows)

        if total < self.MIN_SAMPLE_SIZE:
            return {
                'status': 'insufficient_sample',
                'sample_size': total,
                'minimum_required': self.MIN_SAMPLE_SIZE,
            }

        # Compute components
        hypothesis_valid_count = sum(1 for r in rows if r.get('hypothesis_valid'))
        exit_per_plan_count = sum(1 for r in rows if r.get('exit_per_plan'))
        bias_interference_count = sum(1 for r in rows if r.get('outcome_type') == 'bias_interference')
        regime_aligned_count = sum(1 for r in rows if r.get('outcome_type') != 'regime_mismatch')

        si = round(hypothesis_valid_count / total, 3)
        ed = round(exit_per_plan_count / total, 3)
        bi = round(bias_interference_count / total, 3)
        ra = round(regime_aligned_count / total, 3)

        score = EdgeLabEdgeScore.compute(
            structural_integrity=si,
            execution_discipline=ed,
            bias_interference_rate=bi,
            regime_alignment=ra,
            sample_size=total,
            user_id=user_id,
            window_start=start_date,
            window_end=end_date,
            scope=scope,
        )

        if score:
            self.db.save_edge_score(score)

        return {
            'status': 'computed',
            'data': score.to_api_dict() if score else None,
        }

    def get_edge_score_history(self, user_id: int, days: int = 90) -> List[Dict]:
        """Return saved daily scores for charting."""
        scores = self.db.list_edge_scores(user_id, limit=days)
        return [s.to_api_dict() for s in scores]

    def get_signature_sample_sizes(self, user_id: int) -> List[Dict]:
        """Precompute sample_size per structure_signature for UI ranking.

        Prevents cognitive overfitting on thin data by making cluster size
        visible to the user.
        """
        rows = self.db.get_setup_count_by_signature(user_id)
        result = []
        for row in rows:
            sig = row.get('structure_signature', '')
            count = row.get('setup_count', 0)
            result.append({
                'structureSignature': sig,
                'setupCount': count,
                'firstSeen': str(row.get('first_seen', '')),
                'lastSeen': str(row.get('last_seen', '')),
                'insufficientSample': count < self.MIN_SAMPLE_SIZE,
            })
        return result
