"""
AI Port - Abstract interface for AI/LLM calls.

Abstracts the AI backend (XAI, OpenAI, etc.) so it can be:
- Swapped for different providers
- Mocked for testing
- Extended with new capabilities (web search, function calling)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class AIResponse:
    """Response from an AI call."""
    text: str
    tokens_used: int
    provider: str  # "xai", "openai", etc.
    model: str
    used_web_search: bool = False
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class AIConfig:
    """Configuration for an AI call."""
    timeout: float = 60.0
    temperature: float = 0.7
    max_tokens: int = 600
    enable_web_search: bool = False
    model_override: Optional[str] = None


class AIPort(ABC):
    """
    Abstract interface for AI/LLM calls.

    Provides a unified interface for calling AI models,
    regardless of the underlying provider.
    """

    @abstractmethod
    async def call(
        self,
        system_prompt: str,
        user_message: str,
        config: Optional[AIConfig] = None,
    ) -> AIResponse:
        """
        Call the AI model with a prompt.

        Args:
            system_prompt: System/instructions prompt
            user_message: User message/query
            config: Optional configuration overrides

        Returns:
            AIResponse with the model's response

        Raises:
            AIError: If the AI call fails
        """
        pass

    @abstractmethod
    async def call_with_context(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        config: Optional[AIConfig] = None,
    ) -> AIResponse:
        """
        Call the AI model with conversation history.

        Args:
            system_prompt: System/instructions prompt
            messages: List of {"role": "user"|"assistant", "content": "..."}
            config: Optional configuration overrides

        Returns:
            AIResponse with the model's response

        Raises:
            AIError: If the AI call fails
        """
        pass

    @property
    @abstractmethod
    def default_provider(self) -> str:
        """Get the default provider name (e.g., "xai", "openai")."""
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if any AI provider is configured and available."""
        pass


class AIError(Exception):
    """Base exception for AI-related errors."""
    pass


class AIRateLimitError(AIError):
    """Raised when AI provider rate limits the request."""
    pass


class AITimeoutError(AIError):
    """Raised when AI request times out."""
    pass


class AIProviderError(AIError):
    """Raised when AI provider returns an error."""
    pass
