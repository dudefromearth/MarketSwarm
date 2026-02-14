# services/vexy_ai/capabilities/edge_lab/service.py
"""Edge Lab Report Service — generates doctrine-compliant reports via VexyKernel.reason().

All output is observational. No optimization language. No behavioral recommendations.
No "you should" or "consider." Data is presented; interpretation is the user's.
Edge Lab is a mirror, not a coach.
"""

import aiohttp
from typing import Dict, Any, Optional, List


# Doctrine-compliant system prompt for ALL Edge Lab reports.
# This prevents Vexy from drifting into coaching when it sees correlations.
EDGE_LAB_SYSTEM_PROMPT = """This report is observational. Present data and structural patterns only.
Do not recommend behavioral changes. Do not suggest optimization.
Do not project future probability. Do not use "you should" or "consider."
Do not evaluate performance as good or bad. Data is presented; interpretation
is the user's. Edge Lab is a mirror, not a coach."""


class EdgeLabReportService:
    """Generates structured reports grounded in real trade data."""

    JOURNAL_BASE = "http://localhost:3002"

    REPORT_TYPES = [
        {"id": "structural_summary", "label": "Structural Summary", "desc": "Overview of setup structures and signature clusters"},
        {"id": "attribution_breakdown", "label": "Attribution Breakdown", "desc": "Distribution of outcome types across setups"},
        {"id": "regime_performance", "label": "Regime Performance", "desc": "Structural validity rates by market regime"},
        {"id": "bias_impact", "label": "Bias Impact", "desc": "Readiness state correlation with outcomes"},
        {"id": "edge_score_report", "label": "Edge Score Report", "desc": "Detailed edge score with component analysis"},
        {"id": "campaign_report", "label": "Campaign Report", "desc": "Campaign-scoped setup and outcome summary"},
        {"id": "hypothesis_audit", "label": "Hypothesis Audit", "desc": "Thesis quality and lock rate analysis"},
        {"id": "discipline_tracker", "label": "Discipline Tracker", "desc": "Execution discipline and process adherence"},
        {"id": "pnl_by_attribution", "label": "P&L by Attribution", "desc": "P&L distribution grouped by outcome type (reference only)"},
        {"id": "trade_frequency", "label": "Trade Frequency", "desc": "Setup frequency and timing patterns"},
    ]

    def __init__(self, config: Dict, logger, kernel=None):
        self.config = config
        self.logger = logger
        self.kernel = kernel

    async def _fetch_journal(self, path: str, user_id: int,
                              params: Optional[Dict] = None) -> Any:
        """Fetch data from journal service API."""
        url = f"{self.JOURNAL_BASE}{path}"
        headers = {"X-User-Id": str(user_id), "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result.get("data") if result.get("success") else None
                    return None
        except Exception as e:
            self.logger.warning(f"Edge Lab journal fetch error: {e}")
            return None

    async def _gather_context(self, user_id: int, start_date: Optional[str],
                                end_date: Optional[str]) -> Dict[str, Any]:
        """Gather all Edge Lab data needed for report generation."""
        context: Dict[str, Any] = {}

        # Fetch setups
        params: Dict[str, str] = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        context["setups"] = await self._fetch_journal(
            "/api/edge-lab/setups", user_id, params
        ) or []

        # Fetch analytics if date range provided
        if start_date and end_date:
            context["regime_correlation"] = await self._fetch_journal(
                "/api/edge-lab/analytics/regime-correlation", user_id,
                {"start": start_date, "end": end_date},
            )
            context["bias_overlay"] = await self._fetch_journal(
                "/api/edge-lab/analytics/bias-overlay", user_id,
                {"start": start_date, "end": end_date},
            )
            context["edge_score"] = await self._fetch_journal(
                "/api/edge-lab/analytics/edge-score", user_id,
                {"start": start_date, "end": end_date},
            )

        context["score_history"] = await self._fetch_journal(
            "/api/edge-lab/analytics/edge-score/history", user_id, {"days": "90"},
        ) or []

        context["signatures"] = await self._fetch_journal(
            "/api/edge-lab/analytics/signatures", user_id,
        ) or []

        return context

    def _build_report_prompt(self, report_type: str, context: Dict[str, Any],
                               start_date: Optional[str], end_date: Optional[str]) -> str:
        """Build the user message for kernel.reason() based on report type."""
        date_range = f"from {start_date} to {end_date}" if start_date and end_date else "all time"
        setup_count = len(context.get("setups", []))

        base = f"Generate an Edge Lab {report_type.replace('_', ' ')} report for {date_range}. "
        base += f"Total setups in range: {setup_count}. "

        if report_type == "structural_summary":
            sigs = context.get("signatures", [])
            base += f"Signature clusters: {len(sigs)}. "
            if sigs:
                top = sigs[:5]
                base += "Top signatures by count: " + ", ".join(
                    f"{s.get('structureSignature', '?')} ({s.get('setupCount', 0)} setups)"
                    for s in top
                ) + ". "

        elif report_type == "regime_performance":
            regime = context.get("regime_correlation")
            if regime and regime.get("dimensions"):
                base += f"Total regime-correlated records: {regime.get('total_records', 0)}. "
                dims = regime["dimensions"]
                for dim_name, buckets in dims.items():
                    base += f"{dim_name}: {len(buckets)} buckets. "

        elif report_type == "edge_score_report":
            score = context.get("edge_score")
            if score and score.get("data"):
                d = score["data"]
                base += f"Current score: {d.get('finalScore', 'N/A')}. "
                base += f"SI={d.get('structuralIntegrity')}, ED={d.get('executionDiscipline')}, "
                base += f"BI={d.get('biasInterferenceRate')}, RA={d.get('regimeAlignment')}. "
                base += f"Samples: {d.get('sampleSize')}. "
            elif score and score.get("status") == "insufficient_sample":
                base += f"Insufficient sample size ({score.get('sample_size', 0)} < 10). "

        elif report_type == "bias_impact":
            bias = context.get("bias_overlay")
            if bias and bias.get("dimensions"):
                base += f"Total bias-correlated records: {bias.get('total_records', 0)}. "

        elif report_type == "attribution_breakdown":
            setups = context.get("setups", [])
            type_counts: Dict[str, int] = {}
            for s in setups:
                outcome = s.get("outcome", {})
                if outcome and outcome.get("isConfirmed"):
                    ot = outcome.get("outcomeType", "unknown")
                    type_counts[ot] = type_counts.get(ot, 0) + 1
            if type_counts:
                base += "Outcome distribution: " + ", ".join(
                    f"{k}: {v}" for k, v in type_counts.items()
                ) + ". "

        elif report_type == "hypothesis_audit":
            setups = context.get("setups", [])
            locked = sum(1 for s in setups if s.get("hypothesis", {}).get("isLocked"))
            total_hyp = sum(1 for s in setups if s.get("hypothesis"))
            base += f"Hypotheses logged: {total_hyp}, locked: {locked}. "

        elif report_type == "discipline_tracker":
            setups = context.get("setups", [])
            entry_defined = sum(1 for s in setups if s.get("entryDefined"))
            exit_defined = sum(1 for s in setups if s.get("exitDefined"))
            base += f"Entry defined: {entry_defined}/{setup_count}, exit defined: {exit_defined}/{setup_count}. "

        base += "\nPresent findings as structured observations. No recommendations."
        return base

    async def generate_report(self, report_type: str, user_id: int,
                                user_tier: str = "navigator",
                                start_date: Optional[str] = None,
                                end_date: Optional[str] = None,
                                filters: Optional[Dict] = None) -> Dict[str, Any]:
        """Generate a doctrine-compliant Edge Lab report.

        All LLM calls route through VexyKernel.reason(). No side-channel AI.
        """
        valid_types = {rt["id"] for rt in self.REPORT_TYPES}
        if report_type not in valid_types:
            return {
                "error": f"Unknown report type: {report_type}",
                "valid_types": list(valid_types),
            }

        # Gather data from journal service
        context = await self._gather_context(user_id, start_date, end_date)

        # Build the prompt
        user_message = self._build_report_prompt(report_type, context, start_date, end_date)

        # Call kernel.reason() — the ONLY allowed LLM pathway
        if self.kernel:
            try:
                from core.kernel import ReasoningRequest
                response = await self.kernel.reason(
                    ReasoningRequest(
                        outlet="edge_lab",
                        user_message=user_message,
                        user_id=user_id,
                        tier=user_tier,
                        reflection_dial=0.5,
                        context=context,
                        system_prompt_override=EDGE_LAB_SYSTEM_PROMPT,
                    )
                )
                return {
                    "report_type": report_type,
                    "text": response.text,
                    "data": {
                        "setup_count": len(context.get("setups", [])),
                        "edge_score": context.get("edge_score"),
                        "date_range": {"start": start_date, "end": end_date},
                    },
                    "agent_selected": response.agent_selected,
                    "tokens_used": response.tokens_used,
                }
            except Exception as e:
                self.logger.error(f"Edge Lab kernel.reason() error: {e}")
                return {
                    "report_type": report_type,
                    "text": None,
                    "error": f"Report generation failed: {str(e)}",
                    "data": {
                        "setup_count": len(context.get("setups", [])),
                        "edge_score": context.get("edge_score"),
                        "date_range": {"start": start_date, "end": end_date},
                    },
                }
        else:
            # Kernel not available — return data without LLM analysis
            return {
                "report_type": report_type,
                "text": None,
                "error": "Kernel not available — data-only response",
                "data": {
                    "setup_count": len(context.get("setups", [])),
                    "signatures": context.get("signatures"),
                    "edge_score": context.get("edge_score"),
                    "regime_correlation": context.get("regime_correlation"),
                    "bias_overlay": context.get("bias_overlay"),
                    "date_range": {"start": start_date, "end": end_date},
                },
            }
