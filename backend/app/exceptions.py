"""Application-level exceptions — re-export shim.

All errors now live in ``app.errors``; this module re-exports the most commonly
imported names so existing ``from app.exceptions import ...`` statements
continue to work.
"""

from __future__ import annotations

from app.errors import (
    ErrorCode,
    FileProcessingError,
    HypatiaError,
    LLMProviderError,
    LLMUnavailableError,
    ResourceNotFoundError,
    SettingsError,
)

__all__ = [
    "ErrorCode",
    "FileProcessingError",
    "HypatiaError",
    "LLMProviderError",
    "LLMUnavailableError",
    "ResourceNotFoundError",
    "SettingsError",
]
