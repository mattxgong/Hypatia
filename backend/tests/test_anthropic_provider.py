"""The Anthropic provider's requests and response handling, against a mock HTTP transport."""

from __future__ import annotations

import json
from typing import Any

import anthropic
import httpx
import pytest

from app.errors import ErrorCode, LLMProviderError
from app.services.llm_providers.anthropic_provider import AnthropicProvider


def _provider(response: dict[str, Any], seen: dict[str, Any], model: str | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta")
        return httpx.Response(200, json=response)

    provider = AnthropicProvider(api_key="sk-test", **({"model": model} if model else {}))
    provider._client = anthropic.AsyncAnthropic(
        api_key="sk-test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    return provider


def _message(*, content: list[dict[str, Any]], stop_reason: str = "end_turn", **extra: Any):
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 3, "output_tokens": 1},
        **extra,
    }


async def test_default_request_has_fallbacks_and_no_sampling_params():
    seen: dict[str, Any] = {}
    provider = _provider(
        _message(
            content=[
                {"type": "thinking", "thinking": "", "signature": "sig"},
                {"type": "text", "text": "Hello "},
                {"type": "text", "text": "there."},
            ]
        ),
        seen,
    )

    assert await provider.complete("system", "hi", max_tokens=100) == "Hello there."
    assert seen["body"]["model"] == "claude-sonnet-5-5"
    assert seen["body"]["fallbacks"] == "default"
    assert seen["beta"] == "server-side-fallback-2026-07-01"
    assert "temperature" not in seen["body"]
    assert provider.last_truncated is False


async def test_model_without_server_fallback_gets_a_plain_request():
    seen: dict[str, Any] = {}
    provider = _provider(
        _message(content=[{"type": "text", "text": "ok"}]), seen, model="claude-haiku-5-5"
    )

    await provider.complete("system", "hi", max_tokens=100)
    assert "fallbacks" not in seen["body"]
    assert seen["beta"] is None


async def test_refusal_becomes_a_clear_error():
    provider = _provider(
        _message(
            content=[],
            stop_reason="refusal",
            stop_details={"type": "refusal", "category": "cyber", "explanation": None},
        ),
        {},
    )

    with pytest.raises(LLMProviderError) as caught:
        await provider.complete("system", "hi", max_tokens=100)
    assert caught.value.code == ErrorCode.LLM_RESPONSE_INVALID
    assert "declined" in caught.value.detail and "cyber" in caught.value.detail


async def test_output_cut_off_at_max_tokens_is_flagged():
    provider = _provider(
        _message(content=[{"type": "text", "text": "partial"}], stop_reason="max_tokens"), {}
    )

    assert await provider.complete("system", "hi", max_tokens=1) == "partial"
    assert provider.last_truncated is True
