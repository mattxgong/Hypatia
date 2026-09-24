"""Tests for CopilotProvider streaming over the SDK's event callbacks."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from copilot.session_events import AssistantMessageDeltaData, SessionErrorData, SessionIdleData

from app.errors import LLMProviderError
from app.services.llm_providers.copilot_provider import CopilotProvider


class _FakeSession:
    def __init__(self, events: list[Any]) -> None:
        self._events = events
        self._handler: Callable[[Any], None] | None = None
        self.disconnect = AsyncMock()

    def on(self, handler: Callable[[Any], None]) -> Callable[[], None]:
        self._handler = handler
        return lambda: None

    async def send(self, prompt: str) -> str:
        assert self._handler is not None
        for data in self._events:
            self._handler(SimpleNamespace(data=data))
        return "message-id"


def _provider_with(session: _FakeSession) -> CopilotProvider:
    provider = CopilotProvider(model="gpt-test")
    client = SimpleNamespace(create_session=AsyncMock(return_value=session))
    provider._client = client  # type: ignore[assignment]
    return provider


async def test_stream_yields_deltas_until_idle() -> None:
    session = _FakeSession(
        [
            AssistantMessageDeltaData(delta_content="Hel", message_id="m"),
            AssistantMessageDeltaData(delta_content="lo", message_id="m"),
            SessionIdleData(),
        ]
    )

    chunks = [c async for c in _provider_with(session).stream("sys", "hi")]

    assert chunks == ["Hel", "lo"]
    session.disconnect.assert_awaited_once()


async def test_stream_raises_session_errors() -> None:
    session = _FakeSession([SessionErrorData(error_type="x", message="model unavailable")])

    with pytest.raises(LLMProviderError, match="model unavailable"):
        _ = [c async for c in _provider_with(session).stream("sys", "hi")]
