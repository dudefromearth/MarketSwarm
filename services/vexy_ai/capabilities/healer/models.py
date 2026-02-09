"""
Healer Models - Data structures for self-healing system.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class HealingStrategy(str, Enum):
    """Available healing strategies."""
    RESTART = "restart"
    FAILOVER = "failover"
    ESCALATE = "escalate"
    WAIT = "wait"  # Wait and retry


class HealingStatus(str, Enum):
    """Status of a healing attempt."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    ESCALATED = "escalated"


class HealingProtocol(BaseModel):
    """Protocol defining how to heal a specific service."""
    service_name: str
    strategies: List[HealingStrategy]  # Ordered list to try
    max_attempts: int = 3
    cooldown_sec: int = 60  # Min time between attempts
    escalate_after: int = 2  # Escalate after N failed attempts


class HealingAttempt(BaseModel):
    """Record of a single healing attempt."""
    service_name: str
    strategy: HealingStrategy
    attempt_number: int
    started_at: str
    completed_at: Optional[str] = None
    status: HealingStatus
    error: Optional[str] = None


class HealerStatusResponse(BaseModel):
    """Response for healer status endpoint."""
    running: bool
    active_healings: int
    total_attempts: int
    successful_healings: int
    failed_healings: int


class HealingHistoryResponse(BaseModel):
    """Response for healing history endpoint."""
    service: str
    attempts: List[HealingAttempt]


class ProtocolsResponse(BaseModel):
    """Response for protocols endpoint."""
    protocols: List[HealingProtocol]
