import logging.handlers
from pathlib import Path

from app.config import settings


def test_pytest_logs_are_isolated_from_runtime_directory() -> None:
    runtime_logs_dir = Path.home() / ".hypatia" / "logs"
    app_file_handlers = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, logging.handlers.RotatingFileHandler)
    ]

    assert settings.logs_dir != runtime_logs_dir
    assert ".pytest_cache" in settings.logs_dir.parts
    assert len(app_file_handlers) == 1
    assert Path(app_file_handlers[0].baseFilename).parent == settings.logs_dir
