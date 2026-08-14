"""Tests for Chat WebSocket + history endpoints (Task 4.6)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from app.config import settings
from app.database import get_session
from app.main import app
from app.models.db_models import Base, ChatMessage, ChatRole


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class TestChatHistory:
    async def test_get_empty_history(self, client: AsyncClient) -> None:
        class_id = uuid.uuid4()
        resp = await client.get(f"/api/classes/{class_id}/chat/history")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_history_with_messages(
        self, client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        class_id = uuid.uuid4()
        async with session_factory() as session:
            for i in range(3):
                session.add(
                    ChatMessage(
                        class_id=class_id,
                        role=ChatRole.USER,
                        content=f"Message {i}",
                    )
                )
            await session.commit()

        resp = await client.get(f"/api/classes/{class_id}/chat/history")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    async def test_history_pagination(
        self, client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        class_id = uuid.uuid4()
        async with session_factory() as session:
            for i in range(10):
                session.add(
                    ChatMessage(
                        class_id=class_id,
                        role=ChatRole.USER,
                        content=f"Message {i}",
                    )
                )
            await session.commit()

        resp = await client.get(f"/api/classes/{class_id}/chat/history?limit=3&offset=0")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    async def test_clear_history(
        self, client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        class_id = uuid.uuid4()
        async with session_factory() as session:
            session.add(ChatMessage(class_id=class_id, role=ChatRole.USER, content="Hello"))
            await session.commit()

        resp = await client.delete(f"/api/classes/{class_id}/chat/history")
        assert resp.status_code == 204

        resp = await client.get(f"/api/classes/{class_id}/chat/history")
        assert resp.json() == []


class TestChatWebSocket:
    async def test_invalid_command_returns_error(self) -> None:
        class_id = uuid.uuid4()
        with TestClient(app) as tc, tc.websocket_connect(f"/api/classes/{class_id}/chat") as ws:
            ws.send_json({"type": "message", "content": "/unknown do something"})
            data = ws.receive_json()
            assert data["type"] == "error"
            assert data["code"] == "INVALID_COMMAND"

    async def test_ask_command_streams(self) -> None:
        class_id = uuid.uuid4()

        async def fake_stream(*args, **kwargs):  # type: ignore[no-untyped-def]
            for chunk in ["chunk1", "chunk2"]:
                yield chunk

        with (
            patch("app.routers.chat.wiki_engine.handle_ask_stream", side_effect=fake_stream),
            patch("app.routers.chat.async_session_factory") as mock_factory,
        ):
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with TestClient(app) as tc, tc.websocket_connect(f"/api/classes/{class_id}/chat") as ws:
                ws.send_json({"type": "message", "content": "What is gravity?"})
                msg1 = ws.receive_json()
                assert msg1["type"] == "chunk"
                assert msg1["content"] == "chunk1"

                msg2 = ws.receive_json()
                assert msg2["type"] == "chunk"
                assert msg2["content"] == "chunk2"

                msg3 = ws.receive_json()
                assert msg3["type"] == "complete"
                assert "message_id" in msg3

    async def test_summarize_command(self) -> None:
        class_id = uuid.uuid4()

        with (
            patch("app.routers.chat.wiki_engine.handle_summarize", new_callable=AsyncMock) as mock,
            patch("app.routers.chat.async_session_factory") as mock_factory,
        ):
            from app.services.wiki_engine import SummarizeResult

            mock.return_value = SummarizeResult(success=True, page_path="concepts/topic.md")
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with TestClient(app) as tc, tc.websocket_connect(f"/api/classes/{class_id}/chat") as ws:
                ws.send_json({"type": "message", "content": "/summarize gravity"})
                data = ws.receive_json()
                assert data["type"] == "complete"
                assert data["result"]["page_path"] == "concepts/topic.md"

    async def test_cancel_message(self) -> None:
        class_id = uuid.uuid4()

        with (
            patch("app.routers.chat.task_manager.cancel_task") as mock_cancel,
            TestClient(app) as tc,
            tc.websocket_connect(f"/api/classes/{class_id}/chat") as ws,
        ):
            ws.send_json({"type": "cancel", "operation_id": "task-123"})
            mock_cancel.assert_called_once_with("task-123")
