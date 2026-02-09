"""
Playbook Capability - User-authored playbook system.

Core Doctrine:
- Playbooks are distilled lived knowledge, not recipes
- Playbooks are written after reflection, not during action
- Extraction, not invention
- "What keeps appearing?" — not "What should your playbook say?"

A Playbook is never created from an empty state.
It emerges from marked material: Journal entries, Retrospective excerpts, ML patterns.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException

from ...core.capability import BaseCapability
from .service import PlaybookService
from .models import (
    MarkFodderRequest,
    PlaybookFodderResponse,
    AuthoringPromptRequest,
    AuthoringPromptResponse,
    PlaybookChatRequest,
    PlaybookChatResponse,
    PlaybookSectionsResponse,
    PlaybookSectionInfo,
    CheckExtractionRequest,
    CheckExtractionResponse,
    ProposeExtractionRequest,
    ExtractionPreviewResponse,
    PromoteCandidateRequest,
    PromoteCandidateResponse,
)


class PlaybookCapability(BaseCapability):
    """
    Playbook authoring and extraction capability.

    Provides endpoints for:
    - GET /api/vexy/playbook/sections - Canonical sections
    - GET /api/vexy/playbook/ui-guidance - UI guidance
    - POST /api/vexy/playbook/fodder - Mark content as fodder
    - POST /api/vexy/playbook/authoring-prompt - Get authoring prompt
    - POST /api/vexy/playbook/chat - Chat during authoring
    - POST /api/vexy/playbook/check-extraction - Check extraction eligibility
    - POST /api/vexy/playbook/propose-extraction - Propose extraction
    - POST /api/vexy/playbook/promote-candidate - Promote to playbook
    - GET /api/vexy/playbook/extraction-guidance - Extraction UI guidance
    """

    name = "playbook"
    version = "1.0.0"
    dependencies = []
    buses_required = []

    def __init__(self, vexy):
        super().__init__(vexy)
        self.service: Optional[PlaybookService] = None

    async def start(self) -> None:
        """Initialize Playbook service."""
        self.service = PlaybookService(self.config, self.logger)
        self.logger.info("Playbook capability started", emoji="📖")

    async def stop(self) -> None:
        """Clean up Playbook service."""
        self.service = None
        self.logger.info("Playbook capability stopped", emoji="📖")

    def get_routes(self) -> APIRouter:
        """Return FastAPI router with Playbook endpoints."""
        router = APIRouter(prefix="/api/vexy/playbook", tags=["Playbook"])

        @router.get("/sections", response_model=PlaybookSectionsResponse)
        async def get_sections():
            """
            Get the canonical playbook sections with prompts.

            All sections are optional - none are required.
            """
            sections = self.service.get_sections()
            return PlaybookSectionsResponse(
                sections=[PlaybookSectionInfo(**s) for s in sections]
            )

        @router.get("/ui-guidance")
        async def get_ui_guidance():
            """
            Get UI guidance for playbook authoring surface.

            Includes visual treatment, layout, and anti-patterns.
            """
            return self.service.get_ui_guidance()

        @router.post("/fodder", response_model=PlaybookFodderResponse)
        async def mark_fodder(request: MarkFodderRequest, user_id: int = 1):
            """
            Mark content as Playbook material (fodder).

            This does NOT create a Playbook - it creates fodder.
            Playbooks are never created from an empty state.
            """
            try:
                result = self.service.mark_fodder(
                    user_id=user_id,
                    source=request.source,
                    source_id=request.source_id,
                    content=request.content,
                    source_label=request.source_label,
                    source_date=request.source_date,
                )
                return PlaybookFodderResponse(**result)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        @router.post("/authoring-prompt", response_model=AuthoringPromptResponse)
        async def get_authoring_prompt(request: AuthoringPromptRequest):
            """
            Get the authoring prompt for a set of fodder items.

            Returns the initial prompt: "Here are the moments you marked. What connects them?"
            """
            prompt = self.service.get_authoring_prompt(request.fodder_items)
            return AuthoringPromptResponse(prompt=prompt)

        @router.post("/chat", response_model=PlaybookChatResponse)
        async def playbook_chat(request: PlaybookChatRequest):
            """
            Handle Vexy chat during playbook authoring.

            Vexy may:
            - Reflect similarities across fodder
            - Point out repeated language
            - Ask clarifying questions
            - Suggest consolidation

            Vexy must NOT:
            - Write the Playbook
            - Suggest optimization
            - Prescribe improvements
            """
            result = await self.service.chat(
                message=request.message,
                fodder_items=request.fodder_items,
                current_sections=request.current_sections,
            )
            return PlaybookChatResponse(**result)

        @router.post("/check-extraction", response_model=CheckExtractionResponse)
        async def check_extraction(request: CheckExtractionRequest):
            """
            Check if content is eligible for playbook extraction.

            Extraction is eligible if:
            - At least one positive signal (recurrence language) is present
            - No negative signals (prescription language) are present
            """
            result = self.service.check_extraction_eligibility(request.phase_content)
            return CheckExtractionResponse(**result)

        @router.post("/propose-extraction", response_model=ExtractionPreviewResponse)
        async def propose_extraction(request: ProposeExtractionRequest):
            """
            Propose extraction from retrospective content.

            Creates a candidate that can later be promoted to a full playbook.
            """
            result = self.service.propose_extraction(
                user_id=request.user_id,
                retro_id=request.retro_id,
                phase_content=request.phase_content,
            )

            if result is None:
                raise HTTPException(
                    status_code=422,
                    detail="Content not eligible for extraction"
                )

            return ExtractionPreviewResponse(**result)

        @router.post("/promote-candidate", response_model=PromoteCandidateResponse)
        async def promote_candidate(request: PromoteCandidateRequest):
            """
            Promote a candidate to a full playbook.

            Promotion rules:
            - No minimum length
            - No required structure
            - Empty Playbook is valid
            - Title without content is valid
            """
            try:
                result = self.service.promote_candidate(
                    candidate_id=request.candidate_id,
                    title=request.title,
                    initial_content=request.initial_content,
                )
                return PromoteCandidateResponse(**result)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e))

        @router.get("/extraction-guidance")
        async def get_extraction_guidance():
            """Get UI guidance for extraction preview."""
            return self.service.get_extraction_ui_guidance()

        return router
