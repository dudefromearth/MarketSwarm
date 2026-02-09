"""
AI Adapter - Implementation of AIPort using shared ai_client.

Wraps the shared/ai_client.py module to provide the AIPort interface.
Supports XAI (Grok) with fallback to OpenAI.
"""

from typing import Any, Dict, List, Optional

from shared.ai_client import call_ai, AIClientConfig, AIResponse as SharedAIResponse

from ...ports.ai import (
    AIPort,
    AIConfig,
    AIResponse,
    AIError,
    AIRateLimitError,
    AITimeoutError,
    AIProviderError,
)


class AIAdapter(AIPort):
    """
    AI adapter using shared/ai_client.py.

    Provides unified interface for AI calls with XAI/OpenAI fallback.
    """

    def __init__(self, config: Dict[str, Any], logger: Any):
        """
        Initialize adapter with configuration.

        Args:
            config: Configuration dict containing API keys
            logger: LogUtil instance
        """
        self.config = config
        self.logger = logger

        # Check if we have any API keys configured
        self._has_xai = bool(self._get_key("XAI_API_KEY"))
        self._has_openai = bool(self._get_key("OPENAI_API_KEY"))

    def _get_key(self, key_name: str) -> str:
        """Get an API key from config."""
        import os

        env = self.config.get("env", {}) or {}

        return (
            self.config.get(key_name) or
            env.get(key_name) or
            os.getenv(key_name) or
            ""
        )

    async def call(
        self,
        system_prompt: str,
        user_message: str,
        config: Optional[AIConfig] = None,
    ) -> AIResponse:
        """Call the AI model with a prompt."""
        if config is None:
            config = AIConfig()

        # Convert to shared client config
        client_config = AIClientConfig(
            timeout=config.timeout,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            enable_web_search=config.enable_web_search,
        )

        if config.model_override:
            if "grok" in config.model_override.lower():
                client_config.xai_model = config.model_override
            else:
                client_config.openai_model = config.model_override

        try:
            # Call shared ai_client
            response: SharedAIResponse = await call_ai(
                system_prompt=system_prompt,
                user_message=user_message,
                config=self.config,
                ai_config=client_config,
                logger=self.logger,
            )

            return AIResponse(
                text=response.text,
                tokens_used=response.tokens_used,
                provider=response.provider,
                model=client_config.xai_model if response.provider == "xai" else client_config.openai_model,
                used_web_search=response.used_web_search,
            )

        except Exception as e:
            # Convert to appropriate AIError
            error_str = str(e).lower()

            if "rate limit" in error_str or "429" in error_str:
                raise AIRateLimitError(str(e)) from e
            elif "timeout" in error_str or "504" in error_str:
                raise AITimeoutError(str(e)) from e
            elif "502" in error_str or "503" in error_str:
                raise AIProviderError(str(e)) from e
            else:
                raise AIError(str(e)) from e

    async def call_with_context(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        config: Optional[AIConfig] = None,
    ) -> AIResponse:
        """Call the AI model with conversation history."""
        # For now, flatten messages into a single user message
        # The shared ai_client doesn't support multi-turn yet
        conversation = "\n\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in messages
        ])

        return await self.call(system_prompt, conversation, config)

    @property
    def default_provider(self) -> str:
        """Get the default provider name."""
        if self._has_xai:
            return "xai"
        elif self._has_openai:
            return "openai"
        else:
            return "none"

    @property
    def is_available(self) -> bool:
        """Check if any AI provider is configured."""
        return self._has_xai or self._has_openai
