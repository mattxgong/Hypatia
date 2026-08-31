"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CompletionResult:
    text: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class UsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    request_count: int = 0
    _by_model: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.request_count += 1
        entry = self._by_model.setdefault(model, {"input_tokens": 0, "output_tokens": 0})
        entry["input_tokens"] += input_tokens
        entry["output_tokens"] += output_tokens

    def to_dict(self) -> dict[str, object]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "request_count": self.request_count,
            "by_model": dict(self._by_model),
        }

    def reset(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.request_count = 0
        self._by_model.clear()


usage_totals = UsageTotals()


class LLMProvider(ABC):
    """Interface that all LLM providers must implement."""

    @abstractmethod
    async def complete(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> str:
        """Send a prompt and return the full response text."""

    @abstractmethod
    async def stream(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> AsyncIterator[str]:
        """Send a prompt and yield response text chunks as they arrive."""
        # Mypy requires a yield in the body for AsyncIterator return type.
        yield ""  # pragma: no cover

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Return available model IDs from this provider."""
