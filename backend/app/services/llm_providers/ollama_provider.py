"""LLM provider talking to Ollama's native API rather than its OpenAI shim.

Ollama exposes two HTTP surfaces. ``/v1/chat/completions`` is an OpenAI
compatibility layer that accepts only the fields OpenAI defines and silently
drops everything else — including ``num_ctx``, so a request through it is
always served in whatever window the server was started with (4096 by default).
``/api/chat`` is the native surface and takes an ``options`` object, which is
the only way for Hypatia to size the context window itself.

The native API also takes ``think: false``, which suppresses chain-of-thought
on reasoning models. That matters here because Ollama returns thinking in a
separate ``thinking`` field: a small model that reasons its way through the
whole output budget leaves ``content`` empty, and Hypatia's ingest prompts get
back nothing at all.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.errors import ErrorCode, LLMProviderError
from app.utils.logging import get_logger

from .base import LLMProvider, usage_totals

logger = get_logger()

#: Generous: a local model on CPU can take minutes over a long ingest prompt.
DEFAULT_TIMEOUT = 600.0


def _wrap_http_error(exc: httpx.HTTPError, model: str) -> LLMProviderError:
    if isinstance(exc, httpx.TimeoutException):
        return LLMProviderError(
            ErrorCode.LLM_TIMEOUT,
            f"Ollama did not respond in time for {model}.",
            "Try a smaller model, or check that the Ollama server is not overloaded.",
        )
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return LLMProviderError(
            ErrorCode.LLM_UNAVAILABLE,
            f"Ollama does not have the model {model}.",
            f"Run `ollama pull {model}`, or pick a different model in Settings.",
        )
    if isinstance(exc, httpx.ConnectError):
        return LLMProviderError(
            ErrorCode.LLM_UNAVAILABLE,
            f"Could not reach the Ollama server: {exc}",
            "Start Ollama (`ollama serve`) and check the base URL in Settings.",
        )
    return LLMProviderError(ErrorCode.LLM_UNAVAILABLE, str(exc))


class OllamaProvider(LLMProvider):
    """Local models served by Ollama, over its native ``/api`` endpoints.

    ``num_ctx`` is the context window to request. Ollama allocates a KV cache
    proportional to it, so this is the caller's decision (see
    ``ollama_manager.choose_context_length``) rather than the model's maximum.
    Left as None, the server's own default applies.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        temperature: float = 0.3,
        num_ctx: int | None = None,
        think: bool = False,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._temperature = temperature
        self._num_ctx = num_ctx
        self._think = think
        self._timeout = timeout

    def _payload(
        self, system_prompt: str, user_prompt: str, max_tokens: int, stream: bool
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "temperature": self._temperature,
            "num_predict": max_tokens,
        }
        if self._num_ctx:
            options["num_ctx"] = self._num_ctx

        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": stream,
            # Accepted by models without a thinking capability too, so this
            # needs no per-model gating.
            "think": self._think,
            "options": options,
        }

    def _record_usage(self, data: dict[str, Any]) -> None:
        prompt_tokens = data.get("prompt_eval_count") or 0
        output_tokens = data.get("eval_count") or 0
        if prompt_tokens or output_tokens:
            usage_totals.record(self._model, prompt_tokens, output_tokens)

    def _check_truncated(self, data: dict[str, Any], max_tokens: int) -> None:
        if data.get("done_reason") == "length":
            logger.warning(
                "ollama_output_truncated",
                model=self._model,
                max_tokens=max_tokens,
                num_ctx=self._num_ctx,
            )

    def _no_answer_error(self, max_tokens: int) -> LLMProviderError:
        return LLMProviderError(
            ErrorCode.LLM_RESPONSE_INVALID,
            f"{self._model} spent its entire {max_tokens}-token output budget on "
            "reasoning and returned no answer.",
            "Pick a model that does not reason by default, or raise "
            "HYPATIA_LLM_CONTEXT_WINDOW to give it more room.",
        )

    async def complete(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> str:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/api/chat",
                    json=self._payload(system_prompt, user_prompt, max_tokens, stream=False),
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.warning("ollama_api_error", model=self._model, error=str(exc))
            raise _wrap_http_error(exc, self._model) from exc

        self._record_usage(data)
        self._check_truncated(data, max_tokens)

        message = data.get("message") or {}
        content = message.get("content") or ""
        if content:
            return str(content)
        if message.get("thinking"):
            raise self._no_answer_error(max_tokens)
        return ""

    async def stream(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> AsyncIterator[str]:
        emitted = False
        thought = False
        payload = self._payload(system_prompt, user_prompt, max_tokens, stream=True)

        try:
            async with (
                httpx.AsyncClient(timeout=self._timeout) as client,
                client.stream("POST", f"{self._base_url}/api/chat", json=payload) as response,
            ):
                response.raise_for_status()
                # Newline-delimited JSON, one object per token batch, the
                # last carrying done=true and the token counts.
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except ValueError:
                        logger.warning("ollama_stream_bad_json", model=self._model)
                        continue

                    message = chunk.get("message") or {}
                    content = message.get("content") or ""
                    if content:
                        emitted = True
                        yield str(content)
                    elif message.get("thinking"):
                        thought = True

                    if chunk.get("done"):
                        self._record_usage(chunk)
                        self._check_truncated(chunk, max_tokens)
        except httpx.HTTPError as exc:
            logger.warning("ollama_stream_error", model=self._model, error=str(exc))
            raise _wrap_http_error(exc, self._model) from exc

        if not emitted and thought:
            raise self._no_answer_error(max_tokens)

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.warning("ollama_list_models_error", error=str(exc))
            raise _wrap_http_error(exc, self._model) from exc

        return [m["name"] for m in data.get("models", []) if m.get("name")]
