"""Application-level exceptions mapped to HTTP error responses."""

from __future__ import annotations


class LLMUnavailableError(Exception):
    """Raised when the configured LLM provider cannot be reached."""

    def __init__(self, detail: str = "LLM provider is unavailable") -> None:
        self.detail = detail
        super().__init__(detail)
