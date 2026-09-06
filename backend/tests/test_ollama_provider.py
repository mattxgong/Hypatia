"""Tests for the native Ollama provider and model introspection."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.errors import ErrorCode, LLMProviderError
from app.services.llm_providers.ollama_provider import OllamaProvider
from app.services.ollama_manager import (
    DEFAULT_CONTEXT_LENGTH,
    MAX_AUTO_CONTEXT_LENGTH,
    OllamaModelInfo,
    cached_context_length,
    choose_context_length,
    clear_context_cache,
    refresh_context_length,
    refresh_if_native_ollama,
    show_model,
)

BASE_URL = "http://localhost:11434"


def _transport(handler: Any) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def _patch_client(transport: httpx.MockTransport) -> Any:
    """Make every AsyncClient this module builds route through ``transport``."""
    real_init = httpx.AsyncClient.__init__

    def init(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    return patch.object(httpx.AsyncClient, "__init__", init)


# --- /api/show introspection ------------------------------------------------


@pytest.mark.asyncio
async def test_show_model_reads_namespaced_context_length():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/show"
        return httpx.Response(
            200,
            json={
                "capabilities": ["tools", "thinking", "completion"],
                # Namespaced by architecture, which is why the parser matches
                # on the suffix rather than a fixed key.
                "model_info": {"general.architecture": "granite", "granite.context_length": 131072},
            },
        )

    with _patch_client(_transport(handler)):
        info = await show_model(BASE_URL, "granite4.2:3b")

    assert info == OllamaModelInfo(context_length=131072, thinks=True)


@pytest.mark.asyncio
async def test_show_model_without_thinking_capability():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "capabilities": ["completion", "tools"],
                "model_info": {"qwen2.context_length": 32768},
            },
        )

    with _patch_client(_transport(handler)):
        info = await show_model(BASE_URL, "qwen2.5:0.5b")

    assert info is not None
    assert info.thinks is False
    assert info.context_length == 32768


@pytest.mark.asyncio
async def test_show_model_returns_none_when_unreachable():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with _patch_client(_transport(handler)):
        assert await show_model(BASE_URL, "llama3.2") is None


def test_choose_context_length_caps_large_models():
    assert choose_context_length(131072) == MAX_AUTO_CONTEXT_LENGTH


def test_choose_context_length_keeps_small_models_whole():
    assert choose_context_length(8192) == 8192


def test_choose_context_length_falls_back_when_unknown():
    assert choose_context_length(None) == DEFAULT_CONTEXT_LENGTH
    assert choose_context_length(0) == DEFAULT_CONTEXT_LENGTH


def test_choose_context_length_never_below_server_default():
    """A tiny model still gets Ollama's own default; asking for less buys nothing."""
    assert choose_context_length(2048) == DEFAULT_CONTEXT_LENGTH


@pytest.mark.asyncio
async def test_refresh_context_length_caches_result():
    clear_context_cache()
    with patch(
        "app.services.ollama_manager.show_model",
        AsyncMock(return_value=OllamaModelInfo(context_length=16384, thinks=False)),
    ):
        chosen = await refresh_context_length(BASE_URL, "mistral")

    assert chosen == 16384
    # Trailing slashes must not produce a second cache entry.
    assert cached_context_length(f"{BASE_URL}/", "mistral") == 16384
    clear_context_cache()


@pytest.mark.asyncio
async def test_refresh_context_length_falls_back_when_show_fails():
    clear_context_cache()
    with patch("app.services.ollama_manager.show_model", AsyncMock(return_value=None)):
        assert await refresh_context_length(BASE_URL, "llama3.2") == DEFAULT_CONTEXT_LENGTH
    clear_context_cache()


@pytest.mark.asyncio
async def test_refresh_if_native_ollama_skips_other_providers():
    clear_context_cache()
    show = AsyncMock(return_value=OllamaModelInfo(context_length=131072, thinks=False))
    with patch("app.services.ollama_manager.show_model", show):
        await refresh_if_native_ollama("copilot-ollama", "granite", BASE_URL)
        await refresh_if_native_ollama("copilot", None, BASE_URL)

    show.assert_not_called()
    assert cached_context_length(BASE_URL, "granite") is None


# --- provider requests ------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_sends_num_ctx_and_disables_thinking():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "hello"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 11,
                "eval_count": 3,
            },
        )

    provider = OllamaProvider(base_url=BASE_URL, model="granite", num_ctx=32768)
    with _patch_client(_transport(handler)):
        result = await provider.complete("sys", "user", max_tokens=512)

    assert result == "hello"
    assert captured["options"]["num_ctx"] == 32768
    assert captured["options"]["num_predict"] == 512
    assert captured["think"] is False
    assert captured["stream"] is False
    assert captured["messages"][0] == {"role": "system", "content": "sys"}


@pytest.mark.asyncio
async def test_complete_omits_num_ctx_when_unset():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "ok"}, "done": True})

    provider = OllamaProvider(base_url=BASE_URL, model="granite")
    with _patch_client(_transport(handler)):
        await provider.complete("sys", "user")

    assert "num_ctx" not in captured["options"]


@pytest.mark.asyncio
async def test_complete_records_usage():
    from app.services.llm_providers.base import usage_totals

    usage_totals.reset()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {"content": "hi"},
                "done": True,
                "prompt_eval_count": 40,
                "eval_count": 7,
            },
        )

    provider = OllamaProvider(base_url=BASE_URL, model="granite")
    with _patch_client(_transport(handler)):
        await provider.complete("sys", "user")

    totals = usage_totals.to_dict()
    assert totals["input_tokens"] == 40
    assert totals["output_tokens"] == 7
    usage_totals.reset()


@pytest.mark.asyncio
async def test_complete_raises_when_model_only_thought():
    """Thinking lives outside `content`, so a reasoning model can return nothing."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {"content": "", "thinking": "Let me consider..."},
                "done": True,
                "done_reason": "length",
            },
        )

    provider = OllamaProvider(base_url=BASE_URL, model="granite", think=True)
    with _patch_client(_transport(handler)), pytest.raises(LLMProviderError) as exc:
        await provider.complete("sys", "user")

    assert exc.value.code == ErrorCode.LLM_RESPONSE_INVALID


@pytest.mark.asyncio
async def test_missing_model_suggests_a_pull():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": 'model "nope" not found'})

    provider = OllamaProvider(base_url=BASE_URL, model="nope")
    with _patch_client(_transport(handler)), pytest.raises(LLMProviderError) as exc:
        await provider.complete("sys", "user")

    assert exc.value.code == ErrorCode.LLM_UNAVAILABLE
    assert "ollama pull nope" in (exc.value.user_action or "")


@pytest.mark.asyncio
async def test_connect_error_maps_to_unavailable():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = OllamaProvider(base_url=BASE_URL, model="granite")
    with _patch_client(_transport(handler)), pytest.raises(LLMProviderError) as exc:
        await provider.complete("sys", "user")

    assert exc.value.code == ErrorCode.LLM_UNAVAILABLE


@pytest.mark.asyncio
async def test_timeout_maps_to_timeout_code():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow")

    provider = OllamaProvider(base_url=BASE_URL, model="granite")
    with _patch_client(_transport(handler)), pytest.raises(LLMProviderError) as exc:
        await provider.complete("sys", "user")

    assert exc.value.code == ErrorCode.LLM_TIMEOUT


@pytest.mark.asyncio
async def test_stream_yields_content_and_records_usage():
    from app.services.llm_providers.base import usage_totals

    usage_totals.reset()
    lines = [
        json.dumps({"message": {"content": "Hel"}, "done": False}),
        json.dumps({"message": {"content": "lo"}, "done": False}),
        json.dumps(
            {
                "message": {"content": ""},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 12,
                "eval_count": 2,
            }
        ),
    ]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content="\n".join(lines).encode())

    provider = OllamaProvider(base_url=BASE_URL, model="granite", num_ctx=8192)
    with _patch_client(_transport(handler)):
        chunks = [c async for c in provider.stream("sys", "user")]

    assert "".join(chunks) == "Hello"
    assert usage_totals.to_dict()["input_tokens"] == 12
    usage_totals.reset()


@pytest.mark.asyncio
async def test_stream_skips_malformed_lines():
    lines = ["not json", json.dumps({"message": {"content": "ok"}, "done": True})]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content="\n".join(lines).encode())

    provider = OllamaProvider(base_url=BASE_URL, model="granite")
    with _patch_client(_transport(handler)):
        chunks = [c async for c in provider.stream("sys", "user")]

    assert "".join(chunks) == "ok"


@pytest.mark.asyncio
async def test_stream_raises_when_only_thinking_streamed():
    lines = [
        json.dumps({"message": {"content": "", "thinking": "hmm"}, "done": False}),
        json.dumps({"message": {"content": ""}, "done": True, "done_reason": "length"}),
    ]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content="\n".join(lines).encode())

    provider = OllamaProvider(base_url=BASE_URL, model="granite", think=True)
    with _patch_client(_transport(handler)), pytest.raises(LLMProviderError) as exc:
        [c async for c in provider.stream("sys", "user")]

    assert exc.value.code == ErrorCode.LLM_RESPONSE_INVALID


@pytest.mark.asyncio
async def test_list_models_reads_api_tags():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={"models": [{"name": "granite4.2:3b"}, {"name": "qwen2.5:0.5b"}, {}]},
        )

    provider = OllamaProvider(base_url=BASE_URL, model="granite")
    with _patch_client(_transport(handler)):
        assert await provider.list_models() == ["granite4.2:3b", "qwen2.5:0.5b"]
