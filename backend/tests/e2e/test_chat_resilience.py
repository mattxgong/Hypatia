"""The chat socket survives bad frames, and commands outlive it.

A command keeps running after its client disconnects and records its result
in chat history, which the frontend reloads when it reconnects.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from starlette.testclient import TestClient

from app.errors import LLMProviderError
from app.main import app
from app.services.wiki_engine import SummarizeResult

pytestmark = pytest.mark.asyncio


def _history(client: TestClient, class_id: str) -> list[dict]:
    resp = client.get(f"/api/classes/{class_id}/chat/history")
    assert resp.status_code == 200
    return list(reversed(resp.json()))


async def test_bad_frames_get_an_error_and_keep_the_socket(
    e2e_client: AsyncClient, e2e_class: dict
) -> None:
    with (
        TestClient(app) as client,
        client.websocket_connect(f"/api/classes/{e2e_class['id']}/chat") as ws,
    ):
        ws.send_text("not json")
        assert ws.receive_json()["code"] == "INVALID_COMMAND"
        ws.send_json(["a", "list"])
        assert ws.receive_json()["code"] == "INVALID_COMMAND"

        ws.send_json({"type": "message", "content": "/help"})
        assert ws.receive_json()["type"] == "complete"


async def test_ask_is_recorded_once(e2e_client: AsyncClient, e2e_class: dict) -> None:
    class_id = e2e_class["id"]
    with TestClient(app) as client:
        with client.websocket_connect(f"/api/classes/{class_id}/chat") as ws:
            ws.send_json({"type": "message", "content": "/ask What is machine learning?"})
            while ws.receive_json()["type"] not in ("complete", "error"):
                pass

        history = _history(client, class_id)
    assert [m["role"] for m in history] == ["user", "assistant"]


async def test_ask_finishes_after_the_client_disconnects(
    e2e_client: AsyncClient, e2e_class: dict
) -> None:
    class_id = e2e_class["id"]

    async def slow_answer(
        session: object, cid: uuid.UUID, query: str, **kwargs: object
    ) -> AsyncIterator[str]:
        yield "First part. "
        await asyncio.sleep(0.3)
        yield "Second part."

    with (
        patch("app.routers.chat.wiki_engine.handle_ask_stream", slow_answer),
        TestClient(app) as client,
    ):
        with client.websocket_connect(f"/api/classes/{class_id}/chat") as ws:
            ws.send_json({"type": "message", "content": "/ask anything"})
            assert ws.receive_json() == {"type": "chunk", "content": "First part. "}
        # The socket is closed now; the answer must still be finished and saved.
        history = await _wait_for_history(client, class_id, 2)

    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[1]["content"] == "First part. Second part."


async def _wait_for_history(client: TestClient, class_id: str, count: int) -> list[dict]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        history = _history(client, class_id)
        if len(history) >= count:
            return history
        await asyncio.sleep(0.05)
    return _history(client, class_id)


async def test_complete_carries_the_saved_message_id(
    e2e_client: AsyncClient, e2e_class: dict
) -> None:
    class_id = e2e_class["id"]
    summary = SummarizeResult(success=True, page_path="pages/synthesis/gravity.md")
    with (
        patch("app.routers.chat.wiki_engine.handle_summarize", AsyncMock(return_value=summary)),
        TestClient(app) as client,
    ):
        with client.websocket_connect(f"/api/classes/{class_id}/chat") as ws:
            ws.send_json({"type": "message", "content": "/summarize gravity"})
            complete = ws.receive_json()
        history = _history(client, class_id)

    assert complete["type"] == "complete"
    assert history[-1]["id"] == complete["message_id"]
    assert history[-1]["content"] == complete["content"]


async def test_failure_after_the_client_disconnects_is_in_history(
    e2e_client: AsyncClient, e2e_class: dict
) -> None:
    class_id = e2e_class["id"]

    async def fail_later(*args: object, **kwargs: object) -> SummarizeResult:
        await asyncio.sleep(0.3)
        raise LLMProviderError(detail="The model is overloaded")

    with (
        patch("app.routers.chat.wiki_engine.handle_summarize", fail_later),
        TestClient(app) as client,
    ):
        with client.websocket_connect(f"/api/classes/{class_id}/chat") as ws:
            ws.send_json({"type": "message", "content": "/summarize gravity"})
            # Only /help returns before the command has run; leave now.
        history = await _wait_for_history(client, class_id, 2)

    assert [m["role"] for m in history] == ["user", "system"]
    assert history[1]["content"] == "Error: The model is overloaded"
    assert history[1]["command"] == "summarize"


async def test_cancel_reaches_a_running_command(e2e_client: AsyncClient, e2e_class: dict) -> None:
    class_id = e2e_class["id"]
    started = asyncio.Event()

    async def wait_for_cancel(
        session: object, cid: uuid.UUID, query: str, **kwargs: object
    ) -> AsyncIterator[str]:
        started.set()
        for _ in range(100):
            await asyncio.sleep(0.02)
            if cancelled:
                yield "stopped"
                return
        yield "never cancelled"

    cancelled: list[str] = []
    with (
        patch("app.routers.chat.wiki_engine.handle_ask_stream", wait_for_cancel),
        patch("app.routers.chat.task_manager.cancel_task", side_effect=cancelled.append),
        TestClient(app) as client,
        client.websocket_connect(f"/api/classes/{class_id}/chat") as ws,
    ):
        ws.send_json({"type": "message", "content": "/ask anything"})
        ws.send_json({"type": "cancel", "operation_id": "op-1"})
        assert ws.receive_json() == {"type": "chunk", "content": "stopped"}

    assert cancelled == ["op-1"]
