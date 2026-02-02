"""
AI Provider Abstraction - Multi-provider AI interface.

Supports:
- OpenAI Assistant API
- Grok API (x.ai)
- Anthropic Claude API
- Local/custom providers

This abstraction allows switching between providers via configuration.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, AsyncIterator
from dataclasses import dataclass
from enum import Enum
import logging
import asyncio


class AIProvider(str, Enum):
    """Supported AI providers."""
    OPENAI = "openai"
    GROK = "grok"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


@dataclass
class AIMessage:
    """A message in an AI conversation."""
    role: str  # "user", "assistant", "system"
    content: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class AIResponse:
    """Response from an AI provider."""
    content: str
    provider: AIProvider
    model: str
    tokens_used: Optional[int] = None
    finish_reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class AIProviderConfig:
    """Configuration for an AI provider."""
    provider: AIProvider
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    model: str = ""
    max_tokens: int = 256
    temperature: float = 0.7
    assistant_id: Optional[str] = None  # For OpenAI Assistants
    extra: Optional[Dict[str, Any]] = None


class BaseAIProvider(ABC):
    """
    Abstract base class for AI providers.

    All provider implementations must inherit from this class
    and implement the required methods.
    """

    def __init__(self, config: AIProviderConfig, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    @property
    @abstractmethod
    def provider_name(self) -> AIProvider:
        """Return the provider identifier."""
        pass

    @abstractmethod
    async def generate(
        self,
        messages: List[AIMessage],
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> AIResponse:
        """
        Generate a response from the AI model.

        Args:
            messages: Conversation history
            system_prompt: Optional system prompt to prepend
            **kwargs: Provider-specific options

        Returns:
            AIResponse with generated content
        """
        pass

    async def generate_stream(
        self,
        messages: List[AIMessage],
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        Generate a streaming response.

        Default implementation yields the full response at once.
        Override for true streaming support.
        """
        response = await self.generate(messages, system_prompt, **kwargs)
        yield response.content

    async def health_check(self) -> bool:
        """Check if the provider is available."""
        try:
            response = await self.generate(
                [AIMessage(role="user", content="test")],
                system_prompt="Reply with 'ok'",
            )
            return len(response.content) > 0
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False


class OpenAIProvider(BaseAIProvider):
    """
    OpenAI API provider.

    Supports both Chat Completions and Assistants API.
    """

    @property
    def provider_name(self) -> AIProvider:
        return AIProvider.OPENAI

    def __init__(self, config: AIProviderConfig, logger: Optional[logging.Logger] = None):
        super().__init__(config, logger)
        self._client = None

    def _get_client(self):
        """Lazy-load OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.api_base,
                )
            except ImportError:
                raise RuntimeError("openai package not installed. Run: pip install openai")
        return self._client

    async def generate(
        self,
        messages: List[AIMessage],
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> AIResponse:
        """Generate using OpenAI Chat Completions."""
        client = self._get_client()

        # Build messages list
        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            api_messages.append({"role": msg.role, "content": msg.content})

        # Allow kwargs to override config defaults
        max_tokens = kwargs.pop("max_tokens", self.config.max_tokens)
        temperature = kwargs.pop("temperature", self.config.temperature)

        response = await client.chat.completions.create(
            model=self.config.model or "gpt-4-turbo-preview",
            messages=api_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

        choice = response.choices[0]

        return AIResponse(
            content=choice.message.content,
            provider=self.provider_name,
            model=response.model,
            tokens_used=response.usage.total_tokens if response.usage else None,
            finish_reason=choice.finish_reason,
        )

    async def generate_with_assistant(
        self,
        messages: List[AIMessage],
        **kwargs,
    ) -> AIResponse:
        """Generate using OpenAI Assistants API."""
        if not self.config.assistant_id:
            raise ValueError("assistant_id required for Assistants API")

        client = self._get_client()

        # Create thread and run
        thread = await client.beta.threads.create()

        for msg in messages:
            await client.beta.threads.messages.create(
                thread_id=thread.id,
                role=msg.role,
                content=msg.content,
            )

        run = await client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=self.config.assistant_id,
        )

        # Poll for completion
        while run.status in ["queued", "in_progress"]:
            await asyncio.sleep(0.5)
            run = await client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id,
            )

        if run.status != "completed":
            raise RuntimeError(f"Assistant run failed: {run.status}")

        # Get messages
        response_messages = await client.beta.threads.messages.list(
            thread_id=thread.id
        )

        # Get the latest assistant message
        for msg in response_messages.data:
            if msg.role == "assistant":
                content = msg.content[0].text.value if msg.content else ""
                return AIResponse(
                    content=content,
                    provider=self.provider_name,
                    model="assistant",
                    metadata={"assistant_id": self.config.assistant_id},
                )

        return AIResponse(
            content="",
            provider=self.provider_name,
            model="assistant",
        )


class GrokProvider(BaseAIProvider):
    """
    Grok API provider (x.ai).

    Uses OpenAI-compatible API format.
    """

    @property
    def provider_name(self) -> AIProvider:
        return AIProvider.GROK

    def __init__(self, config: AIProviderConfig, logger: Optional[logging.Logger] = None):
        super().__init__(config, logger)
        # Set default API base for Grok
        if not config.api_base:
            config.api_base = "https://api.x.ai/v1"
        self._client = None

    def _get_client(self):
        """Lazy-load OpenAI-compatible client for Grok."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.api_base,
                )
            except ImportError:
                raise RuntimeError("openai package not installed. Run: pip install openai")
        return self._client

    async def generate(
        self,
        messages: List[AIMessage],
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> AIResponse:
        """Generate using Grok API."""
        client = self._get_client()

        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            api_messages.append({"role": msg.role, "content": msg.content})

        # Allow kwargs to override config defaults
        max_tokens = kwargs.pop("max_tokens", self.config.max_tokens)
        temperature = kwargs.pop("temperature", self.config.temperature)

        response = await client.chat.completions.create(
            model=self.config.model or "grok-beta",
            messages=api_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

        choice = response.choices[0]

        return AIResponse(
            content=choice.message.content,
            provider=self.provider_name,
            model=response.model,
            tokens_used=response.usage.total_tokens if response.usage else None,
            finish_reason=choice.finish_reason,
        )


class AnthropicProvider(BaseAIProvider):
    """
    Anthropic Claude API provider.
    """

    @property
    def provider_name(self) -> AIProvider:
        return AIProvider.ANTHROPIC

    def __init__(self, config: AIProviderConfig, logger: Optional[logging.Logger] = None):
        super().__init__(config, logger)
        self._client = None

    def _get_client(self):
        """Lazy-load Anthropic client."""
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(api_key=self.config.api_key)
            except ImportError:
                raise RuntimeError("anthropic package not installed. Run: pip install anthropic")
        return self._client

    async def generate(
        self,
        messages: List[AIMessage],
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> AIResponse:
        """Generate using Anthropic Claude API."""
        client = self._get_client()

        api_messages = []
        for msg in messages:
            api_messages.append({"role": msg.role, "content": msg.content})

        # Allow kwargs to override config defaults
        max_tokens = kwargs.pop("max_tokens", self.config.max_tokens)

        response = await client.messages.create(
            model=self.config.model or "claude-sonnet-4-20250514",
            messages=api_messages,
            system=system_prompt or "",
            max_tokens=max_tokens,
            **kwargs,
        )

        content = response.content[0].text if response.content else ""

        return AIResponse(
            content=content,
            provider=self.provider_name,
            model=response.model,
            tokens_used=response.usage.input_tokens + response.usage.output_tokens if response.usage else None,
            finish_reason=response.stop_reason,
        )


# ========== Provider Factory ==========

def create_provider(config: AIProviderConfig, logger: Optional[logging.Logger] = None) -> BaseAIProvider:
    """
    Factory function to create an AI provider instance.

    Args:
        config: Provider configuration
        logger: Optional logger

    Returns:
        Configured AI provider instance
    """
    providers = {
        AIProvider.OPENAI: OpenAIProvider,
        AIProvider.GROK: GrokProvider,
        AIProvider.ANTHROPIC: AnthropicProvider,
    }

    provider_class = providers.get(config.provider)
    if not provider_class:
        raise ValueError(f"Unknown provider: {config.provider}")

    return provider_class(config, logger)


class AIProviderManager:
    """
    Manages multiple AI providers and handles failover.

    Allows configuring a primary and fallback providers.
    """

    def __init__(
        self,
        primary: BaseAIProvider,
        fallback: Optional[BaseAIProvider] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.primary = primary
        self.fallback = fallback
        self.logger = logger or logging.getLogger("AIProviderManager")

    async def generate(
        self,
        messages: List[AIMessage],
        system_prompt: Optional[str] = None,
        use_fallback_on_error: bool = True,
        **kwargs,
    ) -> AIResponse:
        """
        Generate using primary provider, falling back if needed.
        """
        try:
            return await self.primary.generate(messages, system_prompt, **kwargs)
        except Exception as e:
            self.logger.error(f"Primary provider failed: {e}")

            if use_fallback_on_error and self.fallback:
                self.logger.info(f"Trying fallback provider: {self.fallback.provider_name}")
                return await self.fallback.generate(messages, system_prompt, **kwargs)

            raise

    async def health_check(self) -> Dict[str, bool]:
        """Check health of all configured providers."""
        results = {}

        results[self.primary.provider_name.value] = await self.primary.health_check()

        if self.fallback:
            results[self.fallback.provider_name.value] = await self.fallback.health_check()

        return results
