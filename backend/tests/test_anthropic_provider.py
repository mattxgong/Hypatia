"""The Anthropic provider's requests and response handling, against a mock HTTP transport."""

from __future__ import annotations

import json
from typing import Any

import anthropic
import httpx
import pytest

from app.errors import ErrorCode, LLMProviderError
from app.services.llm_providers.anthropic_provider import _THINKING_HEADROOM, AnthropicProvider


def _sse(message: dict[str, Any]) -> str:
    """``message`` as the server-sent events of a streamed response."""
    start = {**message, "content": [], "stop_reason": None, "stop_details": None}
    events: list[dict[str, Any]] = [{"type": "message_start", "message": start}]
    for index, block in enumerate(message["content"]):
        if block["type"] == "thinking":
            empty = {"type": "thinking", "thinking": "", "signature": ""}
            delta = {"type": "signature_delta", "signature": block["signature"]}
        else:
            empty = {"type": "text", "text": ""}
            delta = {"type": "text_delta", "text": block["text"]}
        events += [
            {"type": "content_block_start", "index": index, "content_block": empty},
            {"type": "content_block_delta", "index": index, "delta": delta},
            {"type": "content_block_stop", "index": index},
        ]
    events += [
        {
            "type": "message_delta",
            "delta": {
                "stop_reason": message["stop_reason"],
                "stop_sequence": None,
                "stop_details": message.get("stop_details"),
            },
            "usage": {"output_tokens": message["usage"]["output_tokens"]},
        },
        {"type": "message_stop"},
    ]
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)


def _provider(
    response: dict[str, Any],
    seen: dict[str, Any],
    model: str | None = None,
    *,
    model_max_tokens: int | None = 128_000,
):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.startswith("/v1/models/"):
            if model_max_tokens is None:
                return httpx.Response(
                    404, json={"type": "error", "error": {"type": "not_found_error"}}
                )
            info = {
                "type": "model",
                "id": request.url.path.rsplit("/", 1)[-1],
                "display_name": "Test model",
                "created_at": "2026-01-01T00:00:00Z",
                "max_tokens": model_max_tokens,
            }
            return httpx.Response(200, json=info)
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta")
        return httpx.Response(
            200, text=_sse(response), headers={"content-type": "text/event-stream"}
        )

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


async def test_thinking_gets_headroom_within_the_models_output_limit():
    seen: dict[str, Any] = {}
    reply = _message(content=[{"type": "text", "text": "ok"}])

    await _provider(reply, seen).complete("system", "hi", max_tokens=8192)
    assert seen["body"]["max_tokens"] == 8192 + _THINKING_HEADROOM

    await _provider(reply, seen, model_max_tokens=20_000).complete("system", "hi", max_tokens=8192)
    assert seen["body"]["max_tokens"] == 20_000


async def test_unknown_output_limit_sends_the_text_budget_unchanged():
    seen: dict[str, Any] = {}
    provider = _provider(
        _message(content=[{"type": "text", "text": "ok"}]), seen, model_max_tokens=None
    )

    assert await provider.complete("system", "hi", max_tokens=8192) == "ok"
    assert seen["body"]["max_tokens"] == 8192
