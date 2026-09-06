"""Tests for settings persistence and credential updates."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.config import settings
from app.models.schemas import SettingsUpdate
from app.routers.settings import update_settings


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
