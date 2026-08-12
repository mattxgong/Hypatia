"""LLM provider using the Anthropic SDK directly."""

from __future__ import annotations

import anthropic

from app.utils.logging import get_logger

from .base import LLMProvider

logger = get_logger()


class AnthropicProvider(LLMProvider):
    """Direct Anthropic API access for users with their own API key."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.3,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._temperature = temperature

    async def complete(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=self._temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        if not response.content:
            return ""
        block = response.content[0]
        return block.text if hasattr(block, "text") else ""

    async def list_models(self) -> list[str]:
        return [self._model]
