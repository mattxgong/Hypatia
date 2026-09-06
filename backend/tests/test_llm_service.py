"""Tests for the LLM service factory and provider abstraction (Task 3A.1)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.services.llm_providers.base import LLMProvider
from app.services.llm_service import (
    DEFAULT_CONTEXT_WINDOW,
    OLLAMA_CONTEXT_WINDOW,
    get_context_window,
    get_llm_provider,
)
from app.services.ollama_manager import (
    MAX_AUTO_CONTEXT_LENGTH,
    OllamaModelInfo,
    clear_context_cache,
    refresh_context_length,
)


def _settings(**overrides: object) -> Settings:
    defaults = {
        "data_dir": "/tmp/test",
        "logs_dir": "/tmp/logs",
        "llm_provider": "copilot",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_factory_returns_copilot_provider():
    provider = get_llm_provider(_settings(llm_provider="copilot"))
    assert isinstance(provider, LLMProvider)
    from app.services.llm_providers.copilot_provider import CopilotProvider

    assert isinstance(provider, CopilotProvider)


def test_factory_returns_anthropic_provider():
    provider = get_llm_provider(_settings(llm_provider="anthropic", anthropic_api_key="sk-test"))
    from app.services.llm_providers.anthropic_provider import AnthropicProvider

    assert isinstance(provider, AnthropicProvider)


def test_factory_anthropic_requires_key():
    with pytest.raises(ValueError, match="HYPATIA_ANTHROPIC_API_KEY"):
        get_llm_provider(_settings(llm_provider="anthropic", anthropic_api_key=None))


def test_factory_returns_openai_provider():
    provider = get_llm_provider(_settings(llm_provider="openai", openai_api_key="sk-test"))
    from app.services.llm_providers.openai_provider import OpenAIProvider

    assert isinstance(provider, OpenAIProvider)


def test_factory_openai_requires_key():
    with pytest.raises(ValueError, match="HYPATIA_OPENAI_API_KEY"):
        get_llm_provider(_settings(llm_provider="openai", openai_api_key=None))


def test_factory_returns_ollama_provider():
    provider = get_llm_provider(_settings(llm_provider="ollama"))
    from app.services.llm_providers.ollama_provider import OllamaProvider

    assert isinstance(provider, OllamaProvider)


def test_factory_passes_resolved_context_to_ollama():
    """The provider must ask for the window prompts were budgeted against."""
    from app.services.llm_providers.ollama_provider import OllamaProvider

    cfg = _settings(llm_provider="ollama", llm_model="granite", llm_context_window=32_768)
    provider = get_llm_provider(cfg)

    assert isinstance(provider, OllamaProvider)
    assert provider._num_ctx == 32_768
    assert provider._think is False


def test_factory_returns_copilot_ollama_provider():
    provider = get_llm_provider(_settings(llm_provider="copilot-ollama"))
    from app.services.llm_providers.copilot_provider import CopilotProvider

    assert isinstance(provider, CopilotProvider)


def test_factory_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown llm_provider"):
        get_llm_provider(_settings(llm_provider="nonexistent"))


async def test_anthropic_complete():
    from app.services.llm_providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider(api_key="sk-test", model="test-model")

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hello world")]

    with patch.object(provider._client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response
        result = await provider.complete("sys prompt", "user prompt")
        assert result == "Hello world"
        mock_create.assert_called_once()


async def test_openai_complete():
    from app.services.llm_providers.openai_provider import OpenAIProvider

    provider = OpenAIProvider(api_key="sk-test", model="test-model")

    mock_choice = MagicMock()
    mock_choice.message.content = "Hello from OpenAI"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch.object(
        provider._client.chat.completions, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_response
        result = await provider.complete("sys", "user")
        assert result == "Hello from OpenAI"


@pytest.mark.parametrize("provider", ["ollama", "copilot-ollama"])
def test_context_window_is_ollama_default_for_local_providers(provider: str):
    """Ollama serves 4096 tokens unless told otherwise, and nothing has told it yet."""
    clear_context_cache()
    assert get_context_window(_settings(llm_provider=provider)) == OLLAMA_CONTEXT_WINDOW


def test_context_window_uses_cached_model_context():
    """Once /api/show has been read, prompts are budgeted against the real window."""
    clear_context_cache()
    cfg = _settings(llm_provider="ollama", llm_model="granite4.2:3b")

    with patch(
        "app.services.ollama_manager.show_model",
        AsyncMock(return_value=OllamaModelInfo(context_length=131_072, thinks=True)),
    ):
        asyncio.run(refresh_context_length(cfg.ollama_base_url, "granite4.2:3b"))

    # Capped rather than the model's full 131072: the KV cache scales with it.
    assert get_context_window(cfg) == MAX_AUTO_CONTEXT_LENGTH
    clear_context_cache()


def test_context_window_ignores_cache_for_copilot_ollama():
    """copilot-ollama goes through an OpenAI transport that drops num_ctx."""
    clear_context_cache()
    cfg = _settings(llm_provider="copilot-ollama", llm_model="granite4.2:3b")

    with patch(
        "app.services.ollama_manager.show_model",
        AsyncMock(return_value=OllamaModelInfo(context_length=131_072, thinks=True)),
    ):
        asyncio.run(refresh_context_length(cfg.ollama_base_url, "granite4.2:3b"))

    assert get_context_window(cfg) == OLLAMA_CONTEXT_WINDOW
    clear_context_cache()


@pytest.mark.parametrize("provider", ["copilot", "anthropic", "openai"])
def test_context_window_is_large_for_hosted_providers(provider: str):
    assert get_context_window(_settings(llm_provider=provider)) == DEFAULT_CONTEXT_WINDOW


@pytest.mark.parametrize("provider", ["ollama", "copilot"])
def test_explicit_context_window_overrides_inference(provider: str):
    cfg = _settings(llm_provider=provider, llm_context_window=32_000)
    assert get_context_window(cfg) == 32_000
