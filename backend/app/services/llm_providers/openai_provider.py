"""LLM provider using the OpenAI SDK (also works with Ollama's compatible endpoint)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import openai

from app.errors import ErrorCode, LLMProviderError
from app.utils.logging import get_logger

from .base import LLMProvider, usage_totals

logger = get_logger()


def _wrap_openai_error(exc: openai.OpenAIError) -> LLMProviderError:
    if isinstance(exc, openai.AuthenticationError):
        return LLMProviderError(ErrorCode.LLM_AUTH_FAILED, str(exc))
    if isinstance(exc, openai.RateLimitError):
        return LLMProviderError(ErrorCode.LLM_RATE_LIMITED, str(exc))
    if isinstance(exc, openai.APITimeoutError):
        return LLMProviderError(ErrorCode.LLM_TIMEOUT, str(exc))
    return LLMProviderError(ErrorCode.LLM_UNAVAILABLE, str(exc))


class OpenAIProvider(LLMProvider):
    """Direct OpenAI API access, or any OpenAI-compatible server (e.g. Ollama)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "gpt-4o",
        temperature: float = 0.3,
    ) -> None:
        self._client = openai.AsyncOpenAI(
            api_key=api_key or "ollama",
            base_url=base_url,
        )
        self._model = model
        self._temperature = temperature

    async def complete(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=self._temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except openai.OpenAIError as exc:
            logger.warning("openai_api_error", error=str(exc))
            raise _wrap_openai_error(exc) from exc
        if response.usage:
            usage_totals.record(
                self._model,
                response.usage.prompt_tokens or 0,
                response.usage.completion_tokens or 0,
            )
        choice = response.choices[0] if response.choices else None
        if choice and choice.message and choice.message.content:
            return choice.message.content
        return ""

    async def stream(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> AsyncIterator[str]:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=self._temperature,
                stream=True,
                stream_options={"include_usage": True},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except openai.OpenAIError as exc:
            logger.warning("openai_api_error", error=str(exc))
            raise _wrap_openai_error(exc) from exc
        try:
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                if chunk.usage:
                    usage_totals.record(
                        self._model,
                        chunk.usage.prompt_tokens or 0,
                        chunk.usage.completion_tokens or 0,
                    )
        except openai.OpenAIError as exc:
            logger.warning("openai_stream_error", error=str(exc))
            raise _wrap_openai_error(exc) from exc

    async def list_models(self) -> list[str]:
        try:
            models = await self._client.models.list()
        except openai.OpenAIError as exc:
            logger.warning("openai_list_models_error", error=str(exc))
            raise _wrap_openai_error(exc) from exc
        return [m.id for m in models.data]
