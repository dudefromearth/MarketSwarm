"""
Trust Boundary Middleware for Vexy AI.

Vexy AI is an internal service — it runs behind SSE Gateway or Vexy Proxy,
both of which validate the JWT and set X-User-* headers.

This middleware enforces the explicit trust model:
- Rejects requests without X-User-Id (no fallback to default user)
- Attaches user identity to request.state for capabilities to read
- Exempts health/status endpoints and internal orchestration
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Paths that do not require user identity
AUTH_EXEMPT_PREFIXES = (
    "/health",
    "/api/vexy/status",
    "/api/vexy/admin/orchestrate",
)


class TrustBoundaryMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow health, status, and internal orchestration without auth
        if any(path.startswith(prefix) for prefix in AUTH_EXEMPT_PREFIXES):
            return await call_next(request)

        # Extract user identity from trusted gateway headers
        user_id_str = request.headers.get("X-User-Id", "").strip()
        if not user_id_str:
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
            )

        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
            )

        # Attach to request state for capabilities
        request.state.user_id = user_id
        request.state.user_tier = request.headers.get("X-User-Tier", "observer")
        request.state.user_email = request.headers.get("X-User-Email", "")

        return await call_next(request)
