# MEL + ADI + Commentary services

# MEL (Model Effectiveness Layer)
from .mel_models import (
    MELSnapshot,
    MELModelScore,
    MELDelta,
    MELConfig,
    ModelState,
    Trend,
    Confidence,
    CoherenceState,
    Session,
)
from .mel import MELOrchestrator
from .mel_api import MELAPIHandler

# ADI (AI Data Interface)
from .adi_models import AIStructureSnapshot
from .adi import ADIOrchestrator
from .adi_api import ADIAPIHandler

# AI Providers
from .ai_providers import (
    AIProviderConfig,
    AIProviderManager,
    AIResponse,
    create_provider,
)

# Commentary
from .commentary_models import (
    CommentaryMessage,
    CommentaryTrigger,
    CommentaryConfig,
    CommentaryCategory,
    TriggerType,
)
from .commentary_triggers import TriggerDetector, PeriodicTriggerScheduler
from .commentary import CommentaryOrchestrator, CommentaryService
from .commentary_api import CommentaryAPIHandler

__all__ = [
    # MEL
    "MELSnapshot",
    "MELModelScore",
    "MELDelta",
    "MELConfig",
    "ModelState",
    "Trend",
    "Confidence",
    "CoherenceState",
    "Session",
    "MELOrchestrator",
    "MELAPIHandler",
    # ADI
    "AIStructureSnapshot",
    "ADIOrchestrator",
    "ADIAPIHandler",
    # AI Providers
    "AIProviderConfig",
    "AIProviderManager",
    "AIResponse",
    "create_provider",
    # Commentary
    "CommentaryMessage",
    "CommentaryTrigger",
    "CommentaryConfig",
    "CommentaryCategory",
    "TriggerType",
    "TriggerDetector",
    "PeriodicTriggerScheduler",
    "CommentaryOrchestrator",
    "CommentaryService",
    "CommentaryAPIHandler",
]
