# services/ml_feedback/experiment_manager.py
"""A/B experiment management with decision logging and stopping rules."""

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import hashlib
import numpy as np

from .config import DEFAULT_CONFIG, MLConfig


@dataclass
class ExperimentResult:
    """Result of experiment evaluation."""
    champion_metrics: Dict[str, float]
    challenger_metrics: Dict[str, float]
    p_value: float
    significant: bool
    winner: str  # 'champion', 'challenger', or 'no_difference'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StoppingDecision:
    """Decision on whether to stop an experiment."""
    stop: bool
    reason: str
    result: Optional[ExperimentResult] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {'stop': self.stop, 'reason': self.reason}
        if self.result:
            d['result'] = self.result.to_dict()
        return d


@dataclass
class Experiment:
    """An A/B experiment."""
    id: int
    experiment_name: str
    champion_model_id: int
    challenger_model_id: int
    traffic_split: float
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    max_duration_days: int
    min_samples_per_arm: int
    early_stop_threshold: float
    champion_samples: int
    challenger_samples: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'experiment_name': self.experiment_name,
            'champion_model_id': self.champion_model_id,
            'challenger_model_id': self.challenger_model_id,
            'traffic_split': self.traffic_split,
            'status': self.status,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'max_duration_days': self.max_duration_days,
            'min_samples_per_arm': self.min_samples_per_arm,
            'early_stop_threshold': self.early_stop_threshold,
            'champion_samples': self.champion_samples,
            'challenger_samples': self.challenger_samples,
        }


class ExperimentManager:
    """Manage A/B experiments with decision logging and auto-stopping."""

    def __init__(self, db=None, config: MLConfig = None):
        self.db = db
        self.config = config or DEFAULT_CONFIG

    async def create_experiment(
        self,
        name: str,
        challenger_model_id: int,
        champion_model_id: Optional[int] = None,
        traffic_split: float = None,
        max_duration_days: int = None,
        min_samples_per_arm: int = None,
        early_stop_threshold: float = None,
        description: str = None,
    ) -> Optional[Experiment]:
        """Create new A/B experiment with stopping rules."""
        if not self.db:
            return None

        # Use defaults from config
        traffic_split = traffic_split or self.config.default_traffic_split
        max_duration_days = max_duration_days or self.config.default_experiment_duration_days
        min_samples_per_arm = min_samples_per_arm or self.config.min_samples_per_arm
        early_stop_threshold = early_stop_threshold or self.config.default_early_stop_threshold

        # Get champion if not provided
        if champion_model_id is None:
            champion = await self._get_champion_model()
            if not champion:
                return None
            champion_model_id = champion['id']

        result = await self.db.execute(
            """INSERT INTO ml_experiments
               (experiment_name, description, champion_model_id, challenger_model_id,
                traffic_split, status, started_at)
               VALUES (%s, %s, %s, %s, %s, 'running', NOW())""",
            [name, description, champion_model_id, challenger_model_id, traffic_split]
        )

        if result and result.lastrowid:
            return await self.get_experiment(result.lastrowid)
        return None

    async def get_experiment(self, experiment_id: int) -> Optional[Experiment]:
        """Get experiment by ID."""
        if not self.db:
            return None

        row = await self.db.fetch_one(
            "SELECT * FROM ml_experiments WHERE id = %s",
            [experiment_id]
        )

        if not row:
            return None

        return Experiment(
            id=row['id'],
            experiment_name=row['experiment_name'],
            champion_model_id=row['champion_model_id'],
            challenger_model_id=row['challenger_model_id'],
            traffic_split=float(row['traffic_split']),
            status=row['status'],
            started_at=row['started_at'],
            ended_at=row.get('ended_at'),
            max_duration_days=self.config.default_experiment_duration_days,
            min_samples_per_arm=self.config.min_samples_per_arm,
            early_stop_threshold=self.config.default_early_stop_threshold,
            champion_samples=row.get('champion_samples', 0),
            challenger_samples=row.get('challenger_samples', 0),
        )

    async def get_active_experiment(self) -> Optional[Experiment]:
        """Get the currently active experiment."""
        if not self.db:
            return None

        row = await self.db.fetch_one(
            "SELECT * FROM ml_experiments WHERE status = 'running' ORDER BY started_at DESC LIMIT 1"
        )

        if not row:
            return None

        return await self.get_experiment(row['id'])

    def route_request(
        self,
        experiment: Experiment,
        idea_id: str,
    ) -> str:
        """Deterministically route idea to champion or challenger.

        Uses idea_id for consistent routing (same idea always gets same arm).
        """
        hash_val = int(hashlib.sha256(
            f"{experiment.id}:{idea_id}".encode()
        ).hexdigest(), 16) % 100

        if hash_val < experiment.traffic_split * 100:
            return 'challenger'
        return 'champion'

    async def check_stopping_rules(self, experiment_id: int) -> StoppingDecision:
        """Check if experiment should stop early."""
        experiment = await self.get_experiment(experiment_id)
        if not experiment:
            return StoppingDecision(stop=True, reason='experiment_not_found')

        if experiment.status != 'running':
            return StoppingDecision(stop=True, reason='already_stopped')

        # Rule 1: Max duration
        days_running = (datetime.utcnow() - experiment.started_at).days
        if days_running >= experiment.max_duration_days:
            return StoppingDecision(stop=True, reason='max_duration')

        # Rule 2: Minimum samples
        samples = await self._get_sample_counts(experiment_id)
        min_samples = min(samples.get('champion', 0), samples.get('challenger', 0))
        if min_samples < experiment.min_samples_per_arm:
            return StoppingDecision(stop=False, reason='insufficient_samples')

        # Rule 3: Early stopping on clear winner
        result = await self.evaluate_experiment(experiment_id)
        if result.p_value < experiment.early_stop_threshold:
            return StoppingDecision(
                stop=True,
                reason='statistical_significance',
                result=result
            )

        return StoppingDecision(stop=False, reason='continue')

    async def _get_sample_counts(self, experiment_id: int) -> Dict[str, int]:
        """Get sample counts per arm."""
        if not self.db:
            return {}

        results = await self.db.fetch_all(
            """SELECT experiment_arm, COUNT(*) as cnt
               FROM ml_decisions
               WHERE experiment_id = %s AND action_taken = 'traded'
               GROUP BY experiment_arm""",
            [experiment_id]
        )

        return {r['experiment_arm']: r['cnt'] for r in results}

    async def evaluate_experiment(self, experiment_id: int) -> ExperimentResult:
        """Evaluate experiment with business metrics."""
        champion_outcomes = await self._get_outcomes(experiment_id, 'champion')
        challenger_outcomes = await self._get_outcomes(experiment_id, 'challenger')

        if not champion_outcomes or not challenger_outcomes:
            return ExperimentResult(
                champion_metrics={},
                challenger_metrics={},
                p_value=1.0,
                significant=False,
                winner='no_difference',
            )

        # Win rate comparison
        ch_win_rate = sum(1 for o in champion_outcomes if o.get('profitable', False)) / len(champion_outcomes)
        cl_win_rate = sum(1 for o in challenger_outcomes if o.get('profitable', False)) / len(challenger_outcomes)

        # Risk-adjusted return comparison
        ch_rars = [o.get('r2r_achieved', 0) for o in champion_outcomes]
        cl_rars = [o.get('r2r_achieved', 0) for o in challenger_outcomes]
        ch_avg_rar = np.mean(ch_rars) if ch_rars else 0
        cl_avg_rar = np.mean(cl_rars) if cl_rars else 0

        # Drawdown comparison
        ch_max_dd = max((o.get('max_adverse_excursion', 0) for o in champion_outcomes), default=0)
        cl_max_dd = max((o.get('max_adverse_excursion', 0) for o in challenger_outcomes), default=0)

        # Statistical test (Welch's t-test for RAR)
        from scipy import stats
        if len(ch_rars) >= 2 and len(cl_rars) >= 2:
            t_stat, p_value = stats.ttest_ind(ch_rars, cl_rars, equal_var=False)
        else:
            p_value = 1.0

        significant = p_value < 0.05
        winner = 'no_difference'
        if significant:
            winner = 'challenger' if cl_avg_rar > ch_avg_rar else 'champion'

        return ExperimentResult(
            champion_metrics={
                'win_rate': ch_win_rate,
                'avg_rar': ch_avg_rar,
                'max_dd': ch_max_dd,
                'sample_count': len(champion_outcomes),
            },
            challenger_metrics={
                'win_rate': cl_win_rate,
                'avg_rar': cl_avg_rar,
                'max_dd': cl_max_dd,
                'sample_count': len(challenger_outcomes),
            },
            p_value=float(p_value),
            significant=significant,
            winner=winner,
        )

    async def _get_outcomes(
        self,
        experiment_id: int,
        arm: str
    ) -> List[Dict[str, Any]]:
        """Get outcomes for an experiment arm."""
        if not self.db:
            return []

        # Join ml_decisions with tracked_ideas to get outcomes
        return await self.db.fetch_all(
            """SELECT
                 d.idea_id,
                 d.original_score,
                 d.ml_score,
                 d.final_score,
                 t.settlement_pnl,
                 t.max_pnl,
                 t.min_pnl,
                 t.entry_context,
                 CASE WHEN t.settlement_pnl > 0 THEN 1 ELSE 0 END as profitable,
                 CASE
                   WHEN t.entry_context IS NOT NULL
                   THEN t.settlement_pnl / NULLIF(
                     JSON_EXTRACT(t.entry_context, '$.risk_unit'), 0
                   )
                   ELSE NULL
                 END as r2r_achieved,
                 CASE
                   WHEN t.min_pnl IS NOT NULL AND t.entry_context IS NOT NULL
                   THEN ABS(t.min_pnl) / NULLIF(
                     JSON_EXTRACT(t.entry_context, '$.risk_unit'), 0
                   )
                   ELSE NULL
                 END as max_adverse_excursion
               FROM ml_decisions d
               JOIN tracked_ideas t ON d.idea_id = t.id
               WHERE d.experiment_id = %s
                 AND d.experiment_arm = %s
                 AND d.action_taken = 'traded'
                 AND t.settlement_status = 'settled'""",
            [experiment_id, arm]
        )

    async def _get_champion_model(self) -> Optional[Dict[str, Any]]:
        """Get current champion model."""
        if not self.db:
            return None

        return await self.db.fetch_one(
            """SELECT id, model_name, model_version
               FROM ml_models
               WHERE status = 'champion'
               ORDER BY deployed_at DESC
               LIMIT 1"""
        )

    async def conclude_experiment(
        self,
        experiment_id: int,
        winner: str,
        promote_challenger: bool = False,
    ) -> bool:
        """Conclude an experiment and optionally promote challenger."""
        if not self.db:
            return False

        experiment = await self.get_experiment(experiment_id)
        if not experiment or experiment.status != 'running':
            return False

        result = await self.evaluate_experiment(experiment_id)

        # Update experiment status
        await self.db.execute(
            """UPDATE ml_experiments
               SET status = 'concluded',
                   ended_at = NOW(),
                   champion_win_rate = %s,
                   challenger_win_rate = %s,
                   p_value = %s,
                   winner = %s
               WHERE id = %s""",
            [
                result.champion_metrics.get('win_rate'),
                result.challenger_metrics.get('win_rate'),
                result.p_value,
                winner,
                experiment_id,
            ]
        )

        # Promote challenger if requested
        if promote_challenger and winner == 'challenger':
            await self._promote_model(experiment.challenger_model_id)

        return True

    async def _promote_model(self, model_id: int) -> bool:
        """Promote a model to champion status."""
        if not self.db:
            return False

        # Retire current champion
        await self.db.execute(
            """UPDATE ml_models
               SET status = 'retired', retired_at = NOW()
               WHERE status = 'champion'"""
        )

        # Promote new champion
        await self.db.execute(
            """UPDATE ml_models
               SET status = 'champion', deployed_at = NOW()
               WHERE id = %s""",
            [model_id]
        )

        return True

    async def abort_experiment(self, experiment_id: int, reason: str = None) -> bool:
        """Abort a running experiment."""
        if not self.db:
            return False

        await self.db.execute(
            """UPDATE ml_experiments
               SET status = 'aborted', ended_at = NOW()
               WHERE id = %s AND status = 'running'""",
            [experiment_id]
        )

        return True

    async def update_sample_counts(self, experiment_id: int) -> None:
        """Update sample counts for an experiment."""
        if not self.db:
            return

        counts = await self._get_sample_counts(experiment_id)

        await self.db.execute(
            """UPDATE ml_experiments
               SET champion_samples = %s, challenger_samples = %s
               WHERE id = %s""",
            [
                counts.get('champion', 0),
                counts.get('challenger', 0),
                experiment_id,
            ]
        )

    async def list_experiments(
        self,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[Experiment]:
        """List experiments."""
        if not self.db:
            return []

        query = "SELECT * FROM ml_experiments"
        params = []

        if status:
            query += " WHERE status = %s"
            params.append(status)

        query += " ORDER BY started_at DESC LIMIT %s"
        params.append(limit)

        rows = await self.db.fetch_all(query, params)
        experiments = []
        for row in rows:
            exp = await self.get_experiment(row['id'])
            if exp:
                experiments.append(exp)

        return experiments
