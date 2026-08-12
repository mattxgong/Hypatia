"""Tests for the LLM service factory and provider abstraction (Task 3A.1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.services.llm_providers.base import LLMProvider
from app.services.llm_service import get_llm_provider


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
    from app.services.llm_providers.openai_provider import OpenAIProvider

    assert isinstance(provider, OpenAIProvider)


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
