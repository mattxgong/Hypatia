"""LLM provider using the Anthropic SDK directly."""

from __future__ import annotations

from collections.abc import AsyncIterator

import anthropic

from app.errors import ErrorCode, LLMProviderError
from app.utils.logging import get_logger

from .base import LLMProvider, usage_totals

logger = get_logger()


def _wrap_anthropic_error(exc: anthropic.APIError) -> LLMProviderError:
    if isinstance(exc, anthropic.AuthenticationError):
        return LLMProviderError(ErrorCode.LLM_AUTH_FAILED, str(exc))
    if isinstance(exc, anthropic.RateLimitError):
        return LLMProviderError(ErrorCode.LLM_RATE_LIMITED, str(exc))
    if isinstance(exc, anthropic.APITimeoutError):
        return LLMProviderError(ErrorCode.LLM_TIMEOUT, str(exc))
    return LLMProviderError(ErrorCode.LLM_UNAVAILABLE, str(exc))


class AnthropicProvider(LLMProvider):
    """Direct Anthropic API access for users with their own API key."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.3,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._temperature = temperature

    async def complete(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> str:
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=self._temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.APIError as exc:
            logger.warning("anthropic_api_error", error=str(exc))
            raise _wrap_anthropic_error(exc) from exc
        usage_totals.record(
            self._model,
            getattr(response.usage, "input_tokens", 0),
            getattr(response.usage, "output_tokens", 0),
        )
        if not response.content:
            return ""
        block = response.content[0]
        return block.text if hasattr(block, "text") else ""

    async def stream(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> AsyncIterator[str]:
        try:
            stream_ctx = self._client.messages.stream(
                model=self._model,
                max_tokens=max_tokens,
                temperature=self._temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.APIError as exc:
            logger.warning("anthropic_api_error", error=str(exc))
            raise _wrap_anthropic_error(exc) from exc
        try:
            async with stream_ctx as stream:
                async for text in stream.text_stream:
                    yield text
                final = await stream.get_final_message()
                if final and final.usage:
                    usage_totals.record(
                        self._model,
                        getattr(final.usage, "input_tokens", 0),
                        getattr(final.usage, "output_tokens", 0),
                    )
        except anthropic.APIError as exc:
            logger.warning("anthropic_stream_error", error=str(exc))
            raise _wrap_anthropic_error(exc) from exc

    async def list_models(self) -> list[str]:
        return [self._model]
