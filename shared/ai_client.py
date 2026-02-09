"""
AI Client - Unified XAI/OpenAI API interface

Provides a single async function for calling AI APIs with:
- XAI Responses API (primary) with optional web search
- OpenAI chat/completions (fallback)
- Consistent response parsing and error handling
"""

import os
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

import httpx
from fastapi import HTTPException


@dataclass
class AIResponse:
    """Unified response from AI API call."""
    text: str
    tokens_used: int
    provider: str  # 'xai' or 'openai'
    used_web_search: bool = False


@dataclass
class AIClientConfig:
    """Configuration for AI API call."""
    timeout: float = 60.0
    temperature: float = 0.7
    max_tokens: int = 600
    enable_web_search: bool = False
    xai_model: str = "grok-4"
    openai_model: str = "gpt-4o-mini"


def get_api_keys(config: Dict[str, Any]) -> Tuple[str, str]:
    """
    Get API keys using triple-fallback pattern.

    Priority: config dict → config.env dict → environment variable

    Returns:
        Tuple of (xai_key, openai_key)
    """
    env = config.get("env", {}) or {}

    xai_key = (
        config.get("XAI_API_KEY") or
        env.get("XAI_API_KEY") or
        os.getenv("XAI_API_KEY") or
        ""
    )
    openai_key = (
        config.get("OPENAI_API_KEY") or
        env.get("OPENAI_API_KEY") or
        os.getenv("OPENAI_API_KEY") or
        ""
    )

    return xai_key, openai_key


def _parse_xai_response(data: Dict[str, Any]) -> Tuple[str, int, bool]:
    """
    Parse XAI Responses API format.

    Returns:
        Tuple of (text, tokens_used, used_web_search)
    """
    output_items = data.get("output", [])
    narrative_parts = []
    used_web_search = False

    for item in output_items:
        if item.get("type") == "message":
            content = item.get("content", [])
            for c in content:
                if c.get("type") == "output_text":
                    narrative_parts.append(c.get("text", ""))
        elif item.get("type") == "tool_use":
            used_web_search = True

    text = "\n".join(narrative_parts)
    tokens_used = data.get("usage", {}).get("total_tokens", 0)

    return text, tokens_used, used_web_search


def _parse_openai_response(data: Dict[str, Any]) -> Tuple[str, int]:
    """
    Parse OpenAI chat/completions format.

    Returns:
        Tuple of (text, tokens_used)
    """
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    tokens_used = data.get("usage", {}).get("total_tokens", 0)

    return text, tokens_used


async def call_ai(
    system_prompt: str,
    user_message: str,
    config: Dict[str, Any],
    ai_config: Optional[AIClientConfig] = None,
    logger: Optional[Any] = None,
) -> AIResponse:
    """
    Call AI API with unified interface.

    Uses XAI Responses API if XAI_API_KEY is available, otherwise
    falls back to OpenAI chat/completions.

    Args:
        system_prompt: System/instructions prompt
        user_message: User input message
        config: Application config dict (for API keys)
        ai_config: Optional AI configuration (timeout, temp, etc.)
        logger: Optional logger instance

    Returns:
        AIResponse with text, tokens, provider info

    Raises:
        HTTPException on API errors
    """
    if ai_config is None:
        ai_config = AIClientConfig()

    xai_key, openai_key = get_api_keys(config)
    use_xai = bool(xai_key)

    if not xai_key and not openai_key:
        raise HTTPException(status_code=503, detail="No AI API key configured")

    try:
        async with httpx.AsyncClient(timeout=ai_config.timeout) as client:
            if use_xai:
                # Build XAI Responses API payload
                payload: Dict[str, Any] = {
                    "model": ai_config.xai_model,
                    "instructions": system_prompt,
                    "input": user_message,
                    "temperature": ai_config.temperature,
                }

                # Add web search tool if enabled
                if ai_config.enable_web_search:
                    payload["tools"] = [
                        {
                            "type": "web_search",
                            "search_parameters": {
                                "mode": "auto",
                            },
                        }
                    ]

                response = await client.post(
                    "https://api.x.ai/v1/responses",
                    headers={
                        "Authorization": f"Bearer {xai_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            else:
                # OpenAI chat/completions fallback
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": ai_config.openai_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                        "max_tokens": ai_config.max_tokens,
                        "temperature": ai_config.temperature,
                    },
                )

            # Handle rate limiting
            if response.status_code == 429:
                raise HTTPException(status_code=429, detail="AI service rate limited")

            # Handle other errors
            if response.status_code != 200:
                if logger:
                    logger.error(
                        f"AI API error: {response.status_code} - {response.text[:500]}",
                        emoji="❌"
                    )
                raise HTTPException(status_code=502, detail="AI service error")

            data = response.json()

            # Parse response based on provider
            if use_xai:
                text, tokens_used, used_web_search = _parse_xai_response(data)

                if used_web_search and logger:
                    logger.info("Used web search for real-time context", emoji="🌐")
            else:
                text, tokens_used = _parse_openai_response(data)
                used_web_search = False

            if not text:
                raise HTTPException(status_code=502, detail="Empty response from AI")

            return AIResponse(
                text=text.strip(),
                tokens_used=tokens_used,
                provider="xai" if use_xai else "openai",
                used_web_search=used_web_search,
            )

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI service timeout")
    except HTTPException:
        raise
    except Exception as e:
        if logger:
            logger.error(f"AI client error: {e}", emoji="❌")
        raise HTTPException(status_code=500, detail="Internal error")
