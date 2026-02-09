"""
ML Capability - Machine Learning pattern confirmation.

Provides ML-assisted pattern recognition with strict guardrails:
- ML is confirmatory only, never prescriptive
- Silence is always valid
- Never shows during live trading or market stress
- Human always outranks model
"""

from .capability import MLCapability

__all__ = ["MLCapability"]
