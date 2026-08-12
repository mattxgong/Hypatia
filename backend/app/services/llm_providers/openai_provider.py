"""LLM provider using the OpenAI SDK (also works with Ollama's compatible endpoint)."""

from __future__ import annotations

import openai

from app.utils.logging import get_logger

from .base import LLMProvider

logger = get_logger()


class OpenAIProvider(LLMProvider):
    """Direct OpenAI API access, or any OpenAI-compatible server (e.g. Ollama)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "gpt-4o",
        temperature: float = 0.3,
    ) -> None:
        self._client = openai.AsyncOpenAI(
            api_key=api_key or "ollama",
            base_url=base_url,
        )
        self._model = model
        self._temperature = temperature

    async def complete(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        choice = response.choices[0] if response.choices else None
        if choice and choice.message and choice.message.content:
            return choice.message.content
        return ""

    async def list_models(self) -> list[str]:
        models = await self._client.models.list()
        return [m.id for m in models.data]
