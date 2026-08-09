"""Structured JSON logging via structlog.

Every log entry carries ``timestamp``, ``level``, and ``event`` by default.
Call sites bind additional context (``class_id``, ``file_id``, ``operation``,
``correlation_id``) via :func:`bind_context` / ``structlog.contextvars`` so
those fields appear on every subsequent log line until the context is cleared
(typically at the end of a request or a background operation).

Logs are written as JSON lines to a rotating file
(``<logs_dir>/hypatia.log``, 10MB x 5 backups) and mirrored to stdout for
local dev visibility.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import uuid

import structlog

from app.config import settings

_configured = False


def configure_logging() -> None:
    """Idempotently configure stdlib logging + structlog for the process."""
    global _configured
    if _configured:
        return

    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = settings.logs_dir / "hypatia.log"

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    console_handler = logging.StreamHandler(sys.stdout)

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)
    root_logger.handlers = [file_handler, console_handler]

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    _configured = True


def get_logger(**initial_values: object) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger, optionally pre-bound with context values."""
    return structlog.get_logger(**initial_values)


def bind_context(*, correlation_id: str | None = None, **context: object) -> str:
    """Bind context (correlation_id, class_id, file_id, operation, ...) for
    every log call made on this thread/task until :func:`clear_context` runs.

    Generates a correlation_id if one isn't supplied. Returns the id in use
    so callers can propagate it (e.g. in an HTTP response header).
    """
    correlation_id = correlation_id or str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id, **context)
    return correlation_id


def clear_context() -> None:
    """Clear all bound context vars (call at the end of a request/operation)."""
    structlog.contextvars.clear_contextvars()
