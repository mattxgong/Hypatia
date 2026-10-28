"""LLM provider using the Anthropic SDK directly."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import anthropic

from app.errors import ErrorCode, LLMProviderError
from app.utils.logging import get_logger

from .base import LLMProvider, usage_totals

logger = get_logger()

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"

#: Models whose classifier declines can be retried server-side on the model
#: Anthropic recommends for that kind of decline (``fallbacks: "default"``).
_SERVER_FALLBACK_MODELS = frozenset(
    {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
)
_SERVER_FALLBACK_BETA = "server-side-fallback-2026-07-01"

#: Room for adaptive thinking on top of the caller's text budget. Current
#: models think by default and the thinking counts against ``max_tokens``: with
#: only the text budget, ingest spent most of it thinking and was cut off on
#: every chunk, however small. Unused headroom costs nothing.
_THINKING_HEADROOM = 32_000


def _wrap_anthropic_error(exc: anthropic.APIError) -> LLMProviderError:
    if isinstance(exc, anthropic.AuthenticationError):
        return LLMProviderError(ErrorCode.LLM_AUTH_FAILED, str(exc))
    if isinstance(exc, anthropic.RateLimitError):
        return LLMProviderError(ErrorCode.LLM_RATE_LIMITED, str(exc))
    if isinstance(exc, anthropic.APITimeoutError):
        return LLMProviderError(ErrorCode.LLM_TIMEOUT, str(exc))
    return LLMProviderError(ErrorCode.LLM_UNAVAILABLE, str(exc))


def _refusal_error(response: Any) -> LLMProviderError:
    details = getattr(response, "stop_details", None)
    category = getattr(details, "category", None)
    explanation = getattr(details, "explanation", None)
    return LLMProviderError(
        ErrorCode.LLM_RESPONSE_INVALID,
        "The model declined this request"
        + (f" ({category})." if category else ".")
        + (f" {explanation}" if explanation else ""),
        "Rephrase the request, or choose a different model in Settings.",
    )


def _response_text(response: Any) -> str:
    # Thinking runs by default on current models, so text isn't necessarily
    # the first block; join every text block.
    return "".join(
        block.text for block in response.content or [] if getattr(block, "type", "") == "text"
    )


class AnthropicProvider(LLMProvider):
    """Direct Anthropic API access for users with their own API key.

    ``temperature`` is accepted for a uniform provider interface but not sent:
    current Claude models reject non-default sampling parameters.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_ANTHROPIC_MODEL,
        temperature: float = 0.3,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._model_max_tokens: int | None = None
        self._model_max_looked_up = False

    async def _max_tokens(self, text_budget: int) -> int:
        """``text_budget`` plus thinking headroom, within the model's output limit."""
        if not self._model_max_looked_up:
            self._model_max_looked_up = True
            try:
                info = await self._client.models.retrieve(self._model)
                self._model_max_tokens = info.max_tokens
            except anthropic.APIError as exc:
                # Unknown limit: asking for more than the model allows is a 400.
                logger.warning("anthropic_model_info_unavailable", error=str(exc))
        if self._model_max_tokens is None:
            return text_budget
        return min(text_budget + _THINKING_HEADROOM, self._model_max_tokens)

    async def _request(
        self, system_prompt: str, user_prompt: str, max_tokens: int
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": await self._max_tokens(max_tokens),
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if self._model in _SERVER_FALLBACK_MODELS:
            # A declined request is re-run on Anthropic's recommended fallback
            # model inside the same call. Sent untyped: the pinned SDK predates it.
            request["betas"] = [_SERVER_FALLBACK_BETA]
            request["extra_body"] = {"fallbacks": "default"}
        return request

    async def close(self) -> None:
        await self._client.close()

    def _stream(self, request: dict[str, Any]) -> Any:
        if "betas" in request:
            return self._client.beta.messages.stream(**request)
        return self._client.messages.stream(**request)

    async def complete(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> str:
        request = await self._request(system_prompt, user_prompt, max_tokens)
        try:
            # Streamed even though only the final message is used: with thinking
            # headroom the SDK refuses a non-streaming request this long.
            async with self._stream(request) as stream:
                response = await stream.get_final_message()
        except anthropic.APIError as exc:
            logger.warning("anthropic_api_error", error=str(exc))
            raise _wrap_anthropic_error(exc) from exc
        usage_totals.record(
            self._model,
            getattr(response.usage, "input_tokens", 0),
            getattr(response.usage, "output_tokens", 0),
        )
        if response.stop_reason == "refusal":
            raise _refusal_error(response)
        self.last_truncated = response.stop_reason == "max_tokens"
        if self.last_truncated:
            logger.warning(
                "anthropic_output_truncated", model=self._model, max_tokens=request["max_tokens"]
            )
        return _response_text(response)

    async def stream(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> AsyncIterator[str]:
        request = await self._request(system_prompt, user_prompt, max_tokens)
        try:
            async with self._stream(request) as stream:
                async for text in stream.text_stream:
                    yield text
                final = await stream.get_final_message()
                if final and final.usage:
                    usage_totals.record(
                        self._model,
                        getattr(final.usage, "input_tokens", 0),
                        getattr(final.usage, "output_tokens", 0),
                    )
                if final and final.stop_reason == "refusal":
                    raise _refusal_error(final)
        except anthropic.APIError as exc:
            logger.warning("anthropic_stream_error", error=str(exc))
            raise _wrap_anthropic_error(exc) from exc

    async def check(self) -> None:
        # Validates the key and that the model exists, without a completion.
        try:
            await self._client.models.retrieve(self._model)
        except anthropic.APIError as exc:
            raise _wrap_anthropic_error(exc) from exc

    async def list_models(self) -> list[str]:
        return [self._model]
