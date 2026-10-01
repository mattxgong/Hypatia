"""Tests for Chat WebSocket + history endpoints (Task 4.6)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from app.config import settings
from app.database import get_session
from app.errors import LLMUnavailableError
from app.main import app
from app.models.db_models import Base, ChatMessage, ChatRole
from app.services.task_manager import task_manager


def _configure_mock_session(mock_factory: MagicMock) -> MagicMock:
    mock_session = MagicMock(spec=AsyncSession)
    mock_session.commit = AsyncMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_session


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
    async def test_help_command_returns_displayable_content(self) -> None:
        class_id = uuid.uuid4()
        with TestClient(app) as tc, tc.websocket_connect(f"/api/classes/{class_id}/chat") as ws:
            ws.send_json({"type": "message", "content": "/help"})
            data = ws.receive_json()

        assert data["type"] == "complete"
        assert "Available Commands" in data["content"]
        assert data["result"]["command"] == "/help"

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
            _configure_mock_session(mock_factory)

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
            _configure_mock_session(mock_factory)

            with TestClient(app) as tc, tc.websocket_connect(f"/api/classes/{class_id}/chat") as ws:
                ws.send_json({"type": "message", "content": "/summarize gravity"})
                data = ws.receive_json()
                assert data["type"] == "complete"
                assert data["content"] == "Created summary page: concepts/topic.md"
                assert data["result"]["command"] == "/summarize"
                assert data["result"]["page_path"] == "concepts/topic.md"

    async def test_rebuild_unexpected_error_returns_error(self) -> None:
        class_id = uuid.uuid4()

        with (
            patch(
                "app.routers.chat.wiki_engine.handle_rebuild",
                new_callable=AsyncMock,
                side_effect=KeyError("broken rebuild"),
            ),
            patch("app.routers.chat.async_session_factory") as mock_factory,
        ):
            _configure_mock_session(mock_factory)

            with TestClient(app) as tc, tc.websocket_connect(f"/api/classes/{class_id}/chat") as ws:
                ws.send_json({"type": "message", "content": "/rebuild"})
                assert ws.receive_json()["type"] == "progress"
                data = ws.receive_json()
                if data["type"] == "progress":
                    data = ws.receive_json()

        assert data["type"] == "error"
        assert data["code"] == "REBUILD_ERROR"
        assert "broken rebuild" in data["message"]

    async def test_cancel_message(self) -> None:
        class_id = uuid.uuid4()

        with (
            patch("app.routers.chat.task_manager.cancel_task") as mock_cancel,
            TestClient(app) as tc,
            tc.websocket_connect(f"/api/classes/{class_id}/chat") as ws,
        ):
            ws.send_json({"type": "cancel", "operation_id": "task-123"})
            ws.send_json({"type": "message", "content": "/help"})
            assert ws.receive_json()["type"] == "complete"
            mock_cancel.assert_called_once_with("task-123")


class TestStudyCommands:
    async def test_flashcards_fall_back_to_offline_without_an_llm(self) -> None:
        class_id = uuid.uuid4()
        deck = SimpleNamespace(id=uuid.uuid4(), name="entropy flashcards")
        with (
            patch(
                "app.routers.chat.check_llm_available",
                new_callable=AsyncMock,
                side_effect=LLMUnavailableError(),
            ),
            patch("app.routers.chat.study_service") as service,
            patch("app.routers.chat.async_session_factory") as mock_factory,
        ):
            _configure_mock_session(mock_factory)
            service.get_class_or_404 = AsyncMock()
            service.ensure_scope_has_pages = AsyncMock()
            service.generate_deck = AsyncMock(return_value=deck)
            service.deck_cards = AsyncMock(return_value=[1, 2, 3])

            with TestClient(app) as tc, tc.websocket_connect(f"/api/classes/{class_id}/chat") as ws:
                ws.send_json({"type": "message", "content": "/flashcards entropy"})
                data = ws.receive_json()

        assert data["type"] == "complete"
        assert 'Created deck "entropy flashcards" with 3 cards.' in data["content"]
        assert "built offline" in data["content"]
        assert data["result"] == {"command": "/flashcards", "kind": "deck", "id": str(deck.id)}
        request = service.generate_deck.await_args.args[2]
        assert (request.scope.type, request.scope.query, request.method) == (
            "topic",
            "entropy",
            "heuristic",
        )

    async def test_quiz_uses_the_llm_when_available(self) -> None:
        class_id = uuid.uuid4()
        quiz_id = str(uuid.uuid4())

        def start(kind: str, cid: uuid.UUID, request: object) -> str:
            assert (kind, cid, getattr(request, "method", None)) == ("quiz", class_id, "llm")
            task_id = task_manager.start_task("Generate quiz", str(cid))
            task_manager.complete_task(
                task_id, {"kind": "quiz", "id": quiz_id, "name": "All pages quiz", "count": "4"}
            )
            return task_id

        with (
            patch("app.routers.chat.check_llm_available", new_callable=AsyncMock),
            patch("app.routers.chat.study_service") as service,
            patch("app.routers.chat.study_jobs.start_generation", side_effect=start),
            patch("app.routers.chat.async_session_factory") as mock_factory,
        ):
            _configure_mock_session(mock_factory)
            service.get_class_or_404 = AsyncMock()
            service.ensure_scope_has_pages = AsyncMock()

            with TestClient(app) as tc, tc.websocket_connect(f"/api/classes/{class_id}/chat") as ws:
                ws.send_json({"type": "message", "content": "/quiz"})
                data = ws.receive_json()

        assert data["type"] == "complete"
        assert data["content"].startswith('Created quiz "All pages quiz" with 4 questions.')
        assert "offline" not in data["content"]
        assert data["result"] == {"command": "/quiz", "kind": "quiz", "id": quiz_id}

    async def test_failed_generation_reports_an_error(self) -> None:
        class_id = uuid.uuid4()

        def start(kind: str, cid: uuid.UUID, request: object) -> str:
            task_id = task_manager.start_task("Generate flashcards", str(cid))
            task_manager.fail_task(task_id, "LLM error: quota exceeded")
            return task_id

        with (
            patch("app.routers.chat.check_llm_available", new_callable=AsyncMock),
            patch("app.routers.chat.study_service") as service,
            patch("app.routers.chat.study_jobs.start_generation", side_effect=start),
            patch("app.routers.chat.async_session_factory") as mock_factory,
        ):
            _configure_mock_session(mock_factory)
            service.get_class_or_404 = AsyncMock()
            service.ensure_scope_has_pages = AsyncMock()

            with TestClient(app) as tc, tc.websocket_connect(f"/api/classes/{class_id}/chat") as ws:
                ws.send_json({"type": "message", "content": "/flashcards"})
                data = ws.receive_json()

        assert data["type"] == "error"
        assert data["message"] == "LLM error: quota exceeded"


def test_rebuild_summary_lists_removed_restored_and_failed() -> None:
    from app.routers.chat import _rebuild_summary
    from app.services.wiki_engine import RebuildResult

    text = _rebuild_summary(
        RebuildResult(
            success=True,
            pages_created=3,
            pages_preserved=1,
            pages_removed=["pages/concept/old-idea.md"],
            pages_restored=["pages/concept/kept-idea.md"],
            failed_sources=["notes.pdf: LLM error: boom"],
        )
    )

    assert "3 pages written" in text
    assert "- old idea" in text
    assert "- [[kept-idea]]" in text
    assert "- notes.pdf: LLM error: boom" in text
