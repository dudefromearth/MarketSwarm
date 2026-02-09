"""
Playbook Capability Models - Pydantic request/response models.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class MarkFodderRequest(BaseModel):
    """Request to mark content as Playbook material."""
    source: str  # journal, retrospective, ml_pattern, trade, manual
    source_id: str
    content: str
    source_label: Optional[str] = None
    source_date: Optional[str] = None  # ISO date string


class PlaybookFodderResponse(BaseModel):
    """Response with fodder item."""
    id: str
    source: str
    content: str
    source_label: Optional[str] = None
    marked_at: str


class CreatePlaybookRequest(BaseModel):
    """Request to create a playbook from fodder."""
    fodder_ids: List[str]
    name: str = "Untitled"


class AuthoringPromptRequest(BaseModel):
    """Request for authoring prompt."""
    fodder_items: List[Dict[str, Any]]


class AuthoringPromptResponse(BaseModel):
    """Response with authoring prompt."""
    prompt: str


class PlaybookChatRequest(BaseModel):
    """Request for Vexy assistance during playbook authoring."""
    message: str
    fodder_items: List[Dict[str, Any]]
    current_sections: Optional[Dict[str, str]] = None


class PlaybookChatResponse(BaseModel):
    """Response from Vexy playbook chat."""
    response: str
    violations: List[str] = []


class PlaybookSectionInfo(BaseModel):
    """Info about a playbook section."""
    key: str
    title: str
    prompt: str
    description: str


class PlaybookSectionsResponse(BaseModel):
    """Response with playbook sections."""
    sections: List[PlaybookSectionInfo]


class CheckExtractionRequest(BaseModel):
    """Request to check if content is eligible for extraction."""
    phase_content: Dict[str, str]


class CheckExtractionResponse(BaseModel):
    """Response with extraction eligibility."""
    eligible: bool
    reason: str
    positive_signals: List[str] = []
    negative_signals: List[str] = []


class ProposeExtractionRequest(BaseModel):
    """Request to propose extraction from retrospective."""
    user_id: int
    retro_id: str
    phase_content: Dict[str, str]


class ExtractionPreviewResponse(BaseModel):
    """Response with extraction preview."""
    candidate_id: str
    confidence: str
    supporting_quotes: List[str]
    vexy_observation: Optional[str]
    actions: List[str]


class PromoteCandidateRequest(BaseModel):
    """Request to promote candidate to playbook."""
    candidate_id: str
    title: Optional[str] = None
    initial_content: Optional[str] = None


class PromoteCandidateResponse(BaseModel):
    """Response from candidate promotion."""
    playbook_id: str
    title: str
    origin: str
    created_from: str
    fodder_count: int
