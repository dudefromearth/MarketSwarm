# services/vexy_ai/capabilities/edge_lab/capability.py
"""Edge Lab capability — retrospective structural analysis and reporting.

All LLM output routes through VexyKernel.reason() with edge_lab outlet.
Reports are observational only — no optimization, no prediction, no coaching.
"""

from typing import Optional
from fastapi import APIRouter, Request, HTTPException

from core.capability import BaseCapability
from .service import EdgeLabReportService


class EdgeLabCapability(BaseCapability):
    """Edge Lab reporting and analysis capability."""

    name = "edge_lab"
    version = "1.0.0"
    dependencies = []
    buses_required = []

    def __init__(self, vexy):
        super().__init__(vexy)
        self.service: Optional[EdgeLabReportService] = None

    async def start(self) -> None:
        kernel = getattr(self.vexy, 'kernel', None)
        self.service = EdgeLabReportService(
            config=self.config,
            logger=self.logger,
            kernel=kernel,
        )
        self.logger.info("Edge Lab capability started", emoji="🔬")

    async def stop(self) -> None:
        self.service = None
        self.logger.info("Edge Lab capability stopped", emoji="🔬")

    def get_routes(self) -> APIRouter:
        router = APIRouter(tags=["EdgeLab"])

        @router.post("/api/vexy/edge-lab/report")
        async def generate_report(req: Request):
            if not self.service:
                raise HTTPException(status_code=503, detail="Edge Lab not ready")

            user_id_str = req.headers.get("X-User-Id", "")
            user_id = int(user_id_str) if user_id_str else 1
            user_tier = req.headers.get("X-User-Tier", "observer")

            body = await req.json()
            report_type = body.get("report_type") or body.get("reportType")
            if not report_type:
                raise HTTPException(status_code=400, detail="report_type is required")

            start_date = body.get("start") or body.get("startDate")
            end_date = body.get("end") or body.get("endDate")
            filters = body.get("filters", {})

            result = await self.service.generate_report(
                report_type=report_type,
                user_id=user_id,
                user_tier=user_tier,
                start_date=start_date,
                end_date=end_date,
                filters=filters,
            )
            return {"success": True, "data": result}

        @router.get("/api/vexy/edge-lab/report-types")
        async def list_report_types():
            return {
                "success": True,
                "data": EdgeLabReportService.REPORT_TYPES,
            }

        return router
