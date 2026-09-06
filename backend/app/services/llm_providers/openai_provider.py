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


def _reasoning_of(message: object) -> str:
    """Thinking text a server put outside ``content``, if any.

    Not part of the OpenAI schema — Ollama adds ``reasoning``, others use
    ``reasoning_content`` — so it arrives as an undeclared extra field.
    """
    for attr in ("reasoning", "reasoning_content"):
        value = getattr(message, attr, None)
        if isinstance(value, str) and value:
            return value
    return ""


class OpenAIProvider(LLMProvider):
    """Direct OpenAI API access, or any OpenAI-compatible server (e.g. Ollama).

    ``disable_reasoning`` turns off chain-of-thought on servers that support the
    ``reasoning_effort`` knob. Ollama returns a reasoning model's thinking in a
    separate ``reasoning`` field and leaves ``content`` empty, so a model that
    thinks its way through the whole output budget yields nothing at all —
    which is what happens to Hypatia's ingest prompts on a small local model.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "gpt-4o",
        temperature: float = 0.3,
        disable_reasoning: bool = False,
    ) -> None:
        self._client = openai.AsyncOpenAI(
            api_key=api_key or "ollama",
            base_url=base_url,
        )
        self._model = model
        self._temperature = temperature
        # extra_body rather than the typed `reasoning_effort` argument: "none"
        # is an Ollama extension, and the SDK rejects values it doesn't know.
        self._extra_body: dict[str, object] = (
            {"reasoning_effort": "none"} if disable_reasoning else {}
        )

    async def complete(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=self._temperature,
                extra_body=self._extra_body,
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
        message = choice.message if choice else None
        if message and message.content:
            return message.content

        if message and _reasoning_of(message):
            raise LLMProviderError(
                ErrorCode.LLM_RESPONSE_INVALID,
                f"{self._model} spent its entire {max_tokens}-token output budget on "
                "reasoning and returned no answer.",
                "Pick a model that does not reason by default, or raise the context "
                "window (set OLLAMA_CONTEXT_LENGTH on the Ollama server and "
                "HYPATIA_LLM_CONTEXT_WINDOW to match).",
            )
        return ""

    async def stream(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> AsyncIterator[str]:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=self._temperature,
                extra_body=self._extra_body,
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
        emitted = False
        reasoned = False
        try:
            async for chunk in response:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        emitted = True
                        yield delta.content
                    elif _reasoning_of(delta):
                        reasoned = True
                if chunk.usage:
                    usage_totals.record(
                        self._model,
                        chunk.usage.prompt_tokens or 0,
                        chunk.usage.completion_tokens or 0,
                    )
        except openai.OpenAIError as exc:
            logger.warning("openai_stream_error", error=str(exc))
            raise _wrap_openai_error(exc) from exc

        if not emitted and reasoned:
            raise LLMProviderError(
                ErrorCode.LLM_RESPONSE_INVALID,
                f"{self._model} spent its entire {max_tokens}-token output budget on "
                "reasoning and returned no answer.",
                "Pick a model that does not reason by default, or raise the context "
                "window (set OLLAMA_CONTEXT_LENGTH on the Ollama server and "
                "HYPATIA_LLM_CONTEXT_WINDOW to match).",
            )

    async def list_models(self) -> list[str]:
        try:
            models = await self._client.models.list()
        except openai.OpenAIError as exc:
            logger.warning("openai_list_models_error", error=str(exc))
            raise _wrap_openai_error(exc) from exc
        return [m.id for m in models.data]
