"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Interface that all LLM providers must implement."""

    @abstractmethod
    async def complete(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> str:
        """Send a prompt and return the full response text."""

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Return available model IDs from this provider."""
