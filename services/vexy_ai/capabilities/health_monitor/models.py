"""
Health Monitor Models - Data structures for service health tracking.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ServiceStatus(str, Enum):
    """Health status of a service."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ServiceHealth(BaseModel):
    """Health state of a single service."""
    name: str
    status: ServiceStatus
    last_heartbeat: Optional[str] = None  # ISO timestamp
    consecutive_failures: int = 0
    payload: Optional[Dict[str, Any]] = None
    ttl_remaining: Optional[int] = None  # seconds


class HealthEvent(BaseModel):
    """A health state change event."""
    service: str
    previous_status: ServiceStatus
    new_status: ServiceStatus
    timestamp: str
    reason: Optional[str] = None


class HealthMonitorStatusResponse(BaseModel):
    """Response for overall health monitor status."""
    running: bool
    services_monitored: int
    healthy_count: int
    unhealthy_count: int
    last_check: Optional[str] = None


class ServicesHealthResponse(BaseModel):
    """Response for all services health status."""
    services: List[ServiceHealth]
    checked_at: str


class ServiceHistoryResponse(BaseModel):
    """Response for a service's health history."""
    service: str
    current_status: ServiceStatus
    events: List[HealthEvent]
    uptime_percent: Optional[float] = None
