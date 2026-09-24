"""Tests for settings persistence and credential updates."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.config import Settings, settings
from app.errors import ErrorCode, LLMProviderError
from app.models.schemas import SettingsRead, SettingsUpdate, ValidateKeyRequest
from app.routers.settings import _describe_connection_error, update_settings, validate_key
from app.services.settings_store import reconcile_active_model


@pytest.fixture
def original_secrets() -> tuple[str | None, str | None, str | None]:
    original = (
        settings.anthropic_api_key,
        settings.openai_api_key,
        settings.github_token,
    )
    yield original
    settings.anthropic_api_key, settings.openai_api_key, settings.github_token = original


def _request_with_store(store: Mock) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(credential_store=store)))


async def test_update_settings_persists_new_secret(original_secrets: object) -> None:
    store = Mock()

    with patch("app.routers.settings.save_settings"):
        await update_settings(
            SettingsUpdate(openai_api_key="sk-new"),
            _request_with_store(store),  # type: ignore[arg-type]
        )

    store.set.assert_called_once_with("openai_api_key", "sk-new")
    store.delete.assert_not_called()


async def test_update_settings_deletes_cleared_secret(original_secrets: object) -> None:
    store = Mock()
    settings.openai_api_key = "sk-existing"

    with patch("app.routers.settings.save_settings"):
        await update_settings(
            SettingsUpdate(openai_api_key=""),
            _request_with_store(store),  # type: ignore[arg-type]
        )

    assert settings.openai_api_key is None
    store.delete.assert_called_once_with("openai_api_key")
    store.set.assert_not_called()


async def test_update_settings_leaves_omitted_secret_unchanged(original_secrets: object) -> None:
    store = Mock()
    settings.openai_api_key = "sk-existing"

    with patch("app.routers.settings.save_settings"):
        await update_settings(SettingsUpdate(llm_temperature=0.4), _request_with_store(store))  # type: ignore[arg-type]

    assert settings.openai_api_key == "sk-existing"
    store.set.assert_not_called()
    store.delete.assert_not_called()


class _RecordingProvider:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.closed = False

    async def complete(self, *args: object, **kwargs: object) -> str:
        if self.error is not None:
            raise self.error
        return "hi"

    async def close(self) -> None:
        self.closed = True


async def test_validate_key_uses_unsaved_model_and_stored_key(original_secrets: object) -> None:
    settings.github_token = "ghp-stored"
    seen: list[Settings] = []
    provider = _RecordingProvider()

    def fake_get(cfg: Settings) -> _RecordingProvider:
        seen.append(cfg)
        return provider

    with patch("app.services.llm_service.get_llm_provider", side_effect=fake_get):
        resp = await validate_key(ValidateKeyRequest(provider="copilot", model="gpt-unsaved"))

    assert resp.valid is True
    assert seen[0].llm_model == "gpt-unsaved"
    assert seen[0].github_token == "ghp-stored"
    assert settings.llm_model != "gpt-unsaved"
    assert provider.closed is True


async def test_validate_key_reports_unavailable_model_plainly() -> None:
    error = RuntimeError(
        'JSON-RPC Error -32603: Request session.create failed with message: Model "opus-5.5" '
        "is not available."
    )
    provider = _RecordingProvider(error)

    with patch("app.services.llm_service.get_llm_provider", return_value=provider):
        resp = await validate_key(ValidateKeyRequest(provider="copilot", model="opus-5.5"))

    assert resp.valid is False
    assert resp.error == (
        'The model "opus-5.5" is not available on GitHub Copilot. Check the model name.'
    )
    assert provider.closed is True


async def _put(**fields: object) -> SettingsRead:
    with (
        patch("app.routers.settings.save_settings"),
        patch("app.routers.settings.unload_if_ollama", new=AsyncMock()),
        patch("app.routers.settings.refresh_if_native_ollama", new=AsyncMock()),
    ):
        return await update_settings(
            SettingsUpdate(**fields),  # type: ignore[arg-type]
            _request_with_store(Mock()),  # type: ignore[arg-type]
        )


async def test_switching_provider_restores_its_own_model() -> None:
    settings.llm_provider = "copilot"
    settings.llm_model = "gpt-5.4"
    settings.llm_models = {}

    resp = await _put(llm_provider="anthropic")
    assert resp.llm_model is None

    await _put(llm_model="claude-test")
    resp = await _put(llm_provider="copilot")

    assert resp.llm_model == "gpt-5.4"
    assert resp.llm_models["anthropic"] == "claude-test"
    assert resp.llm_models["openai"] is None


async def test_ollama_providers_share_a_model() -> None:
    settings.llm_provider = "ollama"
    settings.llm_model = "qwen3"
    settings.llm_models = {}

    resp = await _put(llm_provider="copilot-ollama")

    assert resp.llm_model == "qwen3"
    assert resp.llm_models["ollama"] == "qwen3"


async def test_provider_and_model_in_one_update_saves_model_for_new_provider() -> None:
    settings.llm_provider = "copilot"
    settings.llm_model = "gpt-5.4"
    settings.llm_models = {}

    resp = await _put(llm_provider="openai", llm_model="gpt-4o")

    assert resp.llm_model == "gpt-4o"
    assert resp.llm_models["copilot"] == "gpt-5.4"
    assert resp.llm_models["openai"] == "gpt-4o"


def test_reconcile_seeds_legacy_single_model() -> None:
    cfg = Settings(llm_provider="copilot", llm_model="gpt-5.4")
    reconcile_active_model(cfg)
    assert cfg.llm_models == {"copilot": "gpt-5.4"}


def test_reconcile_restores_active_providers_model() -> None:
    cfg = Settings(llm_provider="openai", llm_model=None, llm_models={"openai": "gpt-4o"})
    reconcile_active_model(cfg)
    assert cfg.llm_model == "gpt-4o"


async def test_validate_key_uses_the_tested_providers_saved_model() -> None:
    settings.llm_provider = "copilot"
    settings.llm_model = "gpt-5.4"
    settings.llm_models = {"copilot": "gpt-5.4", "anthropic": "claude-test"}
    seen: list[Settings] = []

    def fake_get(cfg: Settings) -> _RecordingProvider:
        seen.append(cfg)
        return _RecordingProvider()

    with patch("app.services.llm_service.get_llm_provider", side_effect=fake_get):
        await validate_key(ValidateKeyRequest(provider="anthropic", api_key="sk-ant"))

    assert seen[0].llm_model == "claude-test"


@pytest.mark.parametrize(
    ("error", "provider", "expected"),
    [
        (
            ValueError("HYPATIA_ANTHROPIC_API_KEY is required for the 'anthropic' provider"),
            "anthropic",
            "Anthropic needs an API key. Enter one and try again.",
        ),
        (
            LLMProviderError(ErrorCode.LLM_AUTH_FAILED, "Error code: 401 - invalid x-api-key"),
            "anthropic",
            "Anthropic rejected the API key. Check that it is correct.",
        ),
        (
            TimeoutError(),
            "openai",
            "OpenAI did not respond in time. Try again, or check your connection.",
        ),
        (
            RuntimeError("Error code: 500 - Something odd happened\nTraceback..."),
            "openai",
            "Could not connect to OpenAI: Something odd happened",
        ),
    ],
)
def test_describe_connection_error(error: Exception, provider: str, expected: str) -> None:
    assert _describe_connection_error(error, provider, None) == expected
