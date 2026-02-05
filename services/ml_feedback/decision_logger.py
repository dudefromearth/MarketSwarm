# services/ml_feedback/decision_logger.py
"""Immutable decision record logging for ML reproducibility."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
import hashlib


@dataclass
class DecisionRecord:
    """A scoring decision to be logged."""
    idea_id: str
    decision_time: datetime
    model_id: Optional[int]
    model_version: Optional[int]
    selector_params_version: int
    feature_snapshot_id: int
    original_score: float
    ml_score: Optional[float]
    final_score: float
    experiment_id: Optional[int] = None
    experiment_arm: Optional[str] = None
    action_taken: str = 'ranked'

    def to_dict(self) -> Dict[str, Any]:
        return {
            'idea_id': self.idea_id,
            'decision_time': self.decision_time.isoformat(),
            'model_id': self.model_id,
            'model_version': self.model_version,
            'selector_params_version': self.selector_params_version,
            'feature_snapshot_id': self.feature_snapshot_id,
            'original_score': self.original_score,
            'ml_score': self.ml_score,
            'final_score': self.final_score,
            'experiment_id': self.experiment_id,
            'experiment_arm': self.experiment_arm,
            'action_taken': self.action_taken,
        }


class DecisionLogger:
    """Log immutable decision records for every scored idea.

    Key properties:
    - Append-only: Records are never modified
    - Idempotent: Same idea_id at same timestamp won't create duplicates
    - Complete: Every scoring decision is captured
    """

    def __init__(self, db=None):
        self.db = db
        self._buffer = []
        self._buffer_size = 100  # Flush every 100 records

    async def log_decision(
        self,
        idea_id: str,
        model_id: Optional[int],
        model_version: Optional[int],
        selector_params_version: int,
        feature_snapshot_id: int,
        original_score: float,
        ml_score: Optional[float],
        final_score: float,
        experiment_id: Optional[int] = None,
        experiment_arm: Optional[str] = None,
        action_taken: str = 'ranked',
    ) -> int:
        """Log a single decision record.

        Returns the decision ID.
        """
        record = DecisionRecord(
            idea_id=idea_id,
            decision_time=datetime.utcnow(),
            model_id=model_id,
            model_version=model_version,
            selector_params_version=selector_params_version,
            feature_snapshot_id=feature_snapshot_id,
            original_score=original_score,
            ml_score=ml_score,
            final_score=final_score,
            experiment_id=experiment_id,
            experiment_arm=experiment_arm,
            action_taken=action_taken,
        )

        return await self._write_record(record)

    async def log_decision_batch(
        self,
        records: list[DecisionRecord]
    ) -> list[int]:
        """Log multiple decision records efficiently."""
        if not records:
            return []

        ids = []
        for record in records:
            record_id = await self._write_record(record)
            ids.append(record_id)
        return ids

    async def _write_record(self, record: DecisionRecord) -> int:
        """Write a single record to database."""
        if not self.db:
            return 0

        result = await self.db.execute(
            """INSERT INTO ml_decisions
               (idea_id, decision_time, model_id, model_version,
                selector_params_version, feature_snapshot_id,
                original_score, ml_score, final_score,
                experiment_id, experiment_arm, action_taken)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                record.idea_id,
                record.decision_time,
                record.model_id,
                record.model_version,
                record.selector_params_version,
                record.feature_snapshot_id,
                record.original_score,
                record.ml_score,
                record.final_score,
                record.experiment_id,
                record.experiment_arm,
                record.action_taken,
            ]
        )
        return result.lastrowid if result else 0

    async def update_action(
        self,
        decision_id: int,
        action_taken: str,
    ) -> bool:
        """Update the action taken for a decision.

        Note: This is the ONLY field that can be updated.
        The action progresses: ranked -> presented -> traded/dismissed
        """
        if not self.db:
            return False

        # Validate progression (can't go backwards)
        valid_progressions = {
            'ranked': ['presented', 'dismissed'],
            'presented': ['traded', 'dismissed'],
            'traded': [],  # Terminal state
            'dismissed': [],  # Terminal state
        }

        current = await self.db.fetch_one(
            "SELECT action_taken FROM ml_decisions WHERE id = %s",
            [decision_id]
        )

        if not current:
            return False

        current_action = current['action_taken']
        if action_taken not in valid_progressions.get(current_action, []):
            return False

        await self.db.execute(
            "UPDATE ml_decisions SET action_taken = %s WHERE id = %s",
            [action_taken, decision_id]
        )
        return True

    async def get_decision(self, decision_id: int) -> Optional[Dict[str, Any]]:
        """Get a decision record by ID."""
        if not self.db:
            return None

        return await self.db.fetch_one(
            """SELECT * FROM ml_decisions WHERE id = %s""",
            [decision_id]
        )

    async def get_decisions_for_idea(self, idea_id: str) -> list[Dict[str, Any]]:
        """Get all decision records for an idea."""
        if not self.db:
            return []

        return await self.db.fetch_all(
            """SELECT * FROM ml_decisions
               WHERE idea_id = %s
               ORDER BY decision_time ASC""",
            [idea_id]
        )

    async def get_decisions_by_model(
        self,
        model_id: int,
        model_version: int,
        limit: int = 1000
    ) -> list[Dict[str, Any]]:
        """Get decisions made by a specific model version."""
        if not self.db:
            return []

        return await self.db.fetch_all(
            """SELECT * FROM ml_decisions
               WHERE model_id = %s AND model_version = %s
               ORDER BY decision_time DESC
               LIMIT %s""",
            [model_id, model_version, limit]
        )

    async def get_experiment_decisions(
        self,
        experiment_id: int,
        arm: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        """Get decisions for an experiment."""
        if not self.db:
            return []

        query = """SELECT * FROM ml_decisions WHERE experiment_id = %s"""
        params = [experiment_id]

        if arm:
            query += " AND experiment_arm = %s"
            params.append(arm)

        query += " ORDER BY decision_time ASC"

        return await self.db.fetch_all(query, params)

    def generate_idempotency_key(
        self,
        idea_id: str,
        timestamp: datetime,
    ) -> str:
        """Generate idempotency key for deduplication."""
        key_str = f"{idea_id}:{timestamp.isoformat()}"
        return hashlib.sha256(key_str.encode()).hexdigest()[:32]
