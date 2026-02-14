"""
HTTP routes for the Vexy Hydrator service.

Endpoints:
- POST /hydrate         — Hydrate snapshot for a single user
- POST /hydrate/batch   — Hydrate snapshots for multiple users
- GET  /health          — Health check
- GET  /status          — Service status
- GET  /metrics         — Hydration metrics
"""

from fastapi import APIRouter, Request
from typing import Any, Dict

router = APIRouter()


def create_router(engine: Any, logger: Any) -> APIRouter:
    """Create routes bound to a HydrationEngine instance."""

    @router.post("/hydrate")
    async def hydrate(request: Request):
        """Hydrate a single user's cognition snapshot."""
        body = await request.json()
        user_id = body.get("user_id")
        tier = body.get("tier", "observer")
        force = body.get("force", False)

        if not user_id:
            return {"error": "user_id required"}, 400

        result = await engine.hydrate(user_id=user_id, tier=tier, force=force)
        return result

    @router.post("/hydrate/batch")
    async def hydrate_batch(request: Request):
        """Hydrate snapshots for multiple users."""
        body = await request.json()
        users = body.get("users", [])

        if not users:
            return {"error": "users array required"}, 400

        results = []
        for entry in users[:50]:  # Cap at 50 per batch
            uid = entry.get("user_id") if isinstance(entry, dict) else entry
            tier = entry.get("tier", "observer") if isinstance(entry, dict) else "observer"
            result = await engine.hydrate(user_id=uid, tier=tier)
            results.append(result)

        return {"results": results, "count": len(results)}

    @router.get("/health")
    async def health():
        """Health check."""
        return {"status": "healthy", "service": "vexy_hydrator"}

    @router.get("/status")
    async def status():
        """Service status with metrics."""
        metrics = engine.get_metrics()
        return {
            "service": "vexy_hydrator",
            "status": "running",
            "metrics": metrics,
        }

    @router.get("/metrics")
    async def metrics():
        """Hydration metrics."""
        return engine.get_metrics()

    return router
