"""Persist non-secret settings to a JSON file in data_dir."""

from __future__ import annotations

import json
from pathlib import Path

from app.utils.logging import get_logger

logger = get_logger()

_FILENAME = "settings.json"

_PERSISTED_KEYS = frozenset(
    {
        "llm_provider",
        "llm_model",
        "llm_temperature",
        "llm_max_tokens",
        "ollama_base_url",
        "whisper_model_size",
        "whisper_device",
    }
)


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
