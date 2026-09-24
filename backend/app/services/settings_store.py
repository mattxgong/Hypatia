"""Persist non-secret settings to a JSON file in data_dir."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings
from app.services.ollama_manager import is_ollama_provider
from app.utils.logging import get_logger

logger = get_logger()

_FILENAME = "settings.json"

_PERSISTED_KEYS = frozenset(
    {
        "llm_provider",
        "llm_model",
        "llm_models",
        "llm_temperature",
        "llm_max_tokens",
        "ollama_base_url",
        "whisper_model_size",
        "whisper_device",
    }
)


def model_slot(provider: str) -> str:
    """Key under which a provider's model is remembered in ``llm_models``.

    Both Ollama-backed providers serve models from the same server, so they share one.
    """
    return "ollama" if is_ollama_provider(provider) else provider


def remember_model(cfg: Settings, provider: str, model: str | None) -> None:
    models = {k: v for k, v in cfg.llm_models.items() if k != model_slot(provider)}
    if model:
        models[model_slot(provider)] = model
    cfg.llm_models = models


def saved_model(cfg: Settings, provider: str) -> str | None:
    if model_slot(provider) == model_slot(cfg.llm_provider):
        return cfg.llm_model
    return cfg.llm_models.get(model_slot(provider))


def reconcile_active_model(cfg: Settings) -> None:
    """At startup, make ``llm_model`` and ``llm_models`` agree for the active provider.

    An explicit ``llm_model`` (env var, or a settings.json written before per-provider
    models existed) wins; otherwise the active provider's remembered model is restored.
    """
    if cfg.llm_model:
        remember_model(cfg, cfg.llm_provider, cfg.llm_model)
    else:
        cfg.llm_model = cfg.llm_models.get(model_slot(cfg.llm_provider))


def load_settings(data_dir: Path) -> dict[str, object]:
    path = data_dir / _FILENAME
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        return {k: v for k, v in raw.items() if k in _PERSISTED_KEYS}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("settings_load_failed", path=str(path), error=str(exc))
        return {}


def save_settings(data_dir: Path, fields: dict[str, object]) -> None:
    path = data_dir / _FILENAME
    existing = load_settings(data_dir)
    merged = {**existing, **{k: v for k, v in fields.items() if k in _PERSISTED_KEYS}}
    try:
        path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        logger.info("settings_persisted", path=str(path))
    except OSError as exc:
        logger.warning("settings_save_failed", path=str(path), error=str(exc))
