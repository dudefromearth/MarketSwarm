"""
Playbook Service - Business logic for Playbook authoring and extraction.

Core Doctrine:
- Playbooks are distilled lived knowledge, not recipes
- Playbooks are written after reflection, not during action
- Extraction, not invention
- "What keeps appearing?" — not "What should your playbook say?"

All LLM calls route through VexyKernel.reason().
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


class PlaybookService:
    """
    Playbook authoring and extraction service.

    Handles all Playbook-related business logic including:
    - Fodder marking
    - Authoring prompts
    - Chat assistance (via VexyKernel)
    - Extraction eligibility
    - Candidate management

    What moved to kernel: System prompt, call_ai, validate_vexy_response.
    What stays here: Fodder management, extraction, promotion, authoring prompts.
    """

    def __init__(self, config: Dict[str, Any], logger: Any, kernel=None):
        self.config = config
        self.logger = logger
        self.kernel = kernel
        # In-memory storage for candidates (would be persisted in production)
        self._candidates: Dict[str, Any] = {}
        self._fodder: Dict[str, Any] = {}

    def get_sections(self) -> List[Dict[str, str]]:
        """Get the canonical playbook sections with prompts."""
        from services.vexy_ai.playbook_authoring import SECTION_PROMPTS, PlaybookSection

        sections = []
        for section in PlaybookSection:
            info = SECTION_PROMPTS.get(section, {})
            sections.append({
                "key": section.value,
                "title": info.get("title", section.value.replace("_", " ").title()),
                "prompt": info.get("prompt", ""),
                "description": info.get("description", ""),
            })

        return sections

    def get_ui_guidance(self) -> Dict[str, Any]:
        """Get UI guidance for playbook authoring surface."""
        from services.vexy_ai.playbook_authoring import PLAYBOOK_UI_GUIDANCE
        return PLAYBOOK_UI_GUIDANCE

    def mark_fodder(
        self,
        user_id: int,
        source: str,
        source_id: str,
        content: str,
        source_label: Optional[str] = None,
        source_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Mark content as Playbook material (fodder).

        This does NOT create a Playbook - it creates fodder.
        """
        from services.vexy_ai.playbook_authoring import PlaybookFodder, FodderSource

        try:
            source_enum = FodderSource(source)
        except ValueError:
            raise ValueError(f"Invalid source: {source}")

        parsed_date = None
        if source_date:
            try:
                parsed_date = datetime.fromisoformat(source_date)
            except ValueError:
                pass

        fodder = PlaybookFodder.create(
            user_id=user_id,
            source=source_enum,
            source_id=source_id,
            content=content,
            source_date=parsed_date,
            source_label=source_label,
        )

        # Store in memory
        self._fodder[fodder.id] = fodder

        self.logger.info(f"Marked fodder from {source}: {fodder.id[:8]}...", emoji="🌿")

        return {
            "id": fodder.id,
            "source": fodder.source.value,
            "content": fodder.content,
            "source_label": fodder.source_label,
            "marked_at": fodder.marked_at.isoformat(),
        }

    def get_authoring_prompt(self, fodder_items: List[Dict[str, Any]]) -> str:
        """Get the authoring prompt for a set of fodder items."""
        from services.vexy_ai.playbook_authoring import (
            PlaybookFodder,
            FodderSource,
            get_authoring_prompt,
        )

        fodder_objs = self._convert_fodder_items(fodder_items)
        return get_authoring_prompt(fodder_objs)

    async def chat(
        self,
        message: str,
        fodder_items: List[Dict[str, Any]],
        current_sections: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Handle Vexy chat during playbook authoring.

        All LLM calls route through VexyKernel.reason().

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
        fodder_objs = self._convert_fodder_items(fodder_items)

        # Build context from fodder items
        context_parts = ["## Fodder Items\n"]
        for i, f in enumerate(fodder_objs[:10], 1):
            context_parts.append(f"{i}. [{f.source.value}] {f.content[:200]}\n")

        # Add current sections context if provided
        if current_sections:
            context_parts.append("\n## Current Draft Sections\n")
            for section, content in current_sections.items():
                if content:
                    context_parts.append(f"**{section.replace('_', ' ').title()}:** {content[:300]}...\n")

        context_text = "".join(context_parts)

        # Route through kernel
        from services.vexy_ai.kernel import ReasoningRequest

        request = ReasoningRequest(
            outlet="playbook",
            user_message=f"{context_text}\n---\n{message}",
            user_id=1,  # TODO: pass user_id from capability
            tier="navigator",  # TODO: pass tier from capability
            reflection_dial=0.4,
            fodder_items=fodder_items,
            current_sections=current_sections,
        )

        response = await self.kernel.reason(request)

        # Violations now tracked in kernel response
        violations = response.forbidden_violations

        if violations:
            self.logger.warn(
                f"Playbook chat contained forbidden language: {violations}",
                emoji="⚠️"
            )

        return {
            "response": response.text,
            "violations": violations,
        }

    def check_extraction_eligibility(
        self,
        phase_content: Dict[str, str],
    ) -> Dict[str, Any]:
        """Check if content is eligible for playbook extraction."""
        from services.vexy_ai.playbook_extraction import detect_extraction_eligibility

        all_content = " ".join(phase_content.values())
        eligible, positive, negative = detect_extraction_eligibility(all_content)

        reason = "Eligible for extraction"
        if not eligible:
            if negative:
                reason = f"Prescription language detected: {negative[0]}"
            elif not positive:
                reason = "No recurrence/pattern language detected"

        return {
            "eligible": eligible,
            "reason": reason,
            "positive_signals": positive,
            "negative_signals": negative,
        }

    def propose_extraction(
        self,
        user_id: int,
        retro_id: str,
        phase_content: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        """Propose extraction from retrospective content."""
        from services.vexy_ai.playbook_extraction import (
            PlaybookCandidate,
            ExtractionTrigger,
            create_extraction_preview,
            should_propose_extraction,
        )

        # Check if extraction should be proposed
        should_propose, reason = should_propose_extraction(phase_content)

        if not should_propose:
            self.logger.debug(f"Extraction not proposed: {reason}")
            return None

        # Create candidate
        candidate = PlaybookCandidate.create_from_retro(
            user_id=user_id,
            retro_id=retro_id,
            phase_content=phase_content,
            trigger=ExtractionTrigger.RETRO_EMERGENCE,
        )

        # Store candidate
        self._candidates[candidate.id] = candidate

        # Create preview
        preview = create_extraction_preview(candidate)

        self.logger.info(
            f"Proposed extraction: {candidate.id[:8]}... confidence={candidate.confidence.value}",
            emoji="🌿"
        )

        return {
            "candidate_id": candidate.id,
            "confidence": candidate.confidence.value,
            "supporting_quotes": candidate.supporting_quotes,
            "vexy_observation": preview.vexy_observation,
            "actions": preview.actions,
        }

    def promote_candidate(
        self,
        candidate_id: str,
        title: Optional[str] = None,
        initial_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Promote a candidate to a full playbook."""
        from services.vexy_ai.playbook_extraction import promote_candidate_to_playbook

        candidate = self._candidates.get(candidate_id)
        if not candidate:
            raise ValueError(f"Candidate not found: {candidate_id}")

        result = promote_candidate_to_playbook(
            candidate=candidate,
            title=title,
            initial_content=initial_content,
        )

        # Mark candidate as promoted
        candidate.promoted_to_playbook_id = result["playbook_id"]

        self.logger.info(
            f"Promoted candidate {candidate_id[:8]}... to playbook {result['playbook_id'][:8]}...",
            emoji="📖"
        )

        return result

    def get_extraction_ui_guidance(self) -> Dict[str, Any]:
        """Get UI guidance for extraction preview."""
        from services.vexy_ai.playbook_extraction import get_extraction_ui_guidance
        return get_extraction_ui_guidance()

    def _convert_fodder_items(self, fodder_items: List[Dict[str, Any]]) -> List[Any]:
        """Convert dict items to PlaybookFodder objects."""
        from services.vexy_ai.playbook_authoring import PlaybookFodder, FodderSource

        fodder_objs = []
        for item in fodder_items:
            try:
                fodder = PlaybookFodder(
                    id=item.get("id", ""),
                    user_id=item.get("user_id", 1),
                    source=FodderSource(item.get("source", "manual")),
                    source_id=item.get("source_id", ""),
                    content=item.get("content", ""),
                    created_at=datetime.now(),
                    marked_at=datetime.now(),
                    source_label=item.get("source_label"),
                )
                fodder_objs.append(fodder)
            except Exception as e:
                self.logger.warn(f"Skipped invalid fodder item: {e}", emoji="⚠️")
                continue

        return fodder_objs
