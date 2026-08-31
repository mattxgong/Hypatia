"""API integration tests (Task 4.11).

Cross-cutting concerns not covered by individual router tests:
- Delete cascade (DB records for files, wiki pages, chat messages)
- Error format consistency across endpoints
- CORS headers on multiple endpoint types
- WebSocket rebuild progress flow
- Graceful degradation across LLM-dependent and independent endpoints
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from app.config import settings
from app.database import get_session
from app.dependencies import check_llm_available
from app.main import app
from app.models.db_models import (
    Base,
    ChatMessage,
    ChatRole,
    Class,
    FileStatus,
    FileType,
    WikiCategory,
    WikiPage,
)
from app.models.db_models import File as FileRecord


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
    app.dependency_overrides[check_llm_available] = lambda: None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _populate_class(
    session_factory: async_sessionmaker[AsyncSession], class_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        session.add(Class(id=class_id, name="Test Class"))
        await session.flush()
        session.add(
            FileRecord(
                class_id=class_id,
                original_filename="note.md",
                file_type=FileType.MARKDOWN,
                file_size_bytes=10,
                raw_path="/fake/path",
                status=FileStatus.READY,
            )
        )
        session.add(
            WikiPage(
                class_id=class_id,
                path="index.md",
                title="Index",
                category=WikiCategory.INDEX,
                content="# Index",
            )
        )
        session.add(
            ChatMessage(
                class_id=class_id,
                role=ChatRole.USER,
                content="Hello",
            )
        )
        await session.commit()


class TestDeleteCascade:
    async def test_delete_class_cascades_db_records(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        tmp_path: Path,
    ) -> None:
        class_id = uuid.uuid4()
        await _populate_class(session_factory, class_id)

        class_dir = tmp_path / "classes" / str(class_id)
        class_dir.mkdir(parents=True)

        resp = await client.delete(f"/api/classes/{class_id}")
        assert resp.status_code == 204

        async with session_factory() as session:
            files = (
                (await session.execute(select(FileRecord).where(FileRecord.class_id == class_id)))
                .scalars()
                .all()
            )
            pages = (
                (await session.execute(select(WikiPage).where(WikiPage.class_id == class_id)))
                .scalars()
                .all()
            )
            messages = (
                (await session.execute(select(ChatMessage).where(ChatMessage.class_id == class_id)))
                .scalars()
                .all()
            )

            assert len(files) == 0
            assert len(pages) == 0
            assert len(messages) == 0


class TestErrorFormatConsistency:
    async def test_class_not_found_has_detail_and_code(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/classes/{uuid.uuid4()}")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body
        assert "code" in body

    async def test_file_not_found_has_detail_and_code(
        self, client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        class_id = uuid.uuid4()
        async with session_factory() as session:
            session.add(Class(id=class_id, name="C"))
            await session.commit()

        resp = await client.get(f"/api/classes/{class_id}/files/{uuid.uuid4()}")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body
        assert "code" in body

    async def test_wiki_page_not_found_has_detail_and_code(self, client: AsyncClient) -> None:
        class_id = uuid.uuid4()
        resp = await client.get(f"/api/classes/{class_id}/wiki/pages/nonexistent.md")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body
        assert "code" in body

    async def test_task_not_found_has_detail_and_code(self, client: AsyncClient) -> None:
        resp = await client.get("/api/tasks/nonexistent-task-id")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body
        assert "code" in body

    async def test_unhandled_exception_returns_500_with_code(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)

        async def broken_session() -> AsyncIterator[AsyncSession]:
            mock = AsyncMock(spec=AsyncSession)
            mock.execute = AsyncMock(side_effect=RuntimeError("boom"))
            yield mock

        app.dependency_overrides[get_session] = broken_session
        app.dependency_overrides[check_llm_available] = lambda: None
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/classes")
        app.dependency_overrides.clear()

        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == "INTERNAL_ERROR"
        assert "detail" in body


class TestCORSAcrossEndpoints:
    async def test_cors_on_classes(self, client: AsyncClient) -> None:
        resp = await client.options(
            "/api/classes",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" in resp.headers

    async def test_cors_on_health(self, client: AsyncClient) -> None:
        resp = await client.get("/health", headers={"Origin": "http://localhost:3000"})
        assert "access-control-allow-origin" in resp.headers

    async def test_cors_on_wiki(self, client: AsyncClient) -> None:
        class_id = uuid.uuid4()
        resp = await client.get(
            f"/api/classes/{class_id}/wiki/tree",
            headers={"Origin": "http://localhost:3000"},
        )
        assert "access-control-allow-origin" in resp.headers


class TestWebSocketRebuildProgress:
    async def test_rebuild_sends_progress_then_complete(self) -> None:
        class_id = uuid.uuid4()

        async def fake_rebuild(session, cid, task_id=None):  # type: ignore[no-untyped-def]
            from app.services.task_manager import task_manager

            if task_id:
                task_manager.update_progress(task_id, 50, "Halfway there")

        with (
            patch("app.routers.chat.wiki_engine.handle_rebuild", new_callable=AsyncMock) as mock_rb,
            patch("app.routers.chat.async_session_factory") as mock_factory,
        ):
            mock_rb.side_effect = fake_rebuild
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with TestClient(app) as tc, tc.websocket_connect(f"/api/classes/{class_id}/chat") as ws:
                ws.send_json({"type": "message", "content": "/rebuild"})

                first = ws.receive_json()
                assert first["type"] == "progress"
                assert first["percent"] == 0

                messages = [first]
                while True:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg["type"] in ("complete", "error"):
                        break

                assert messages[-1]["type"] == "complete"
                assert "task_id" in messages[-1].get("result", {})

    async def test_rebuild_cancel_stops_operation(self) -> None:
        class_id = uuid.uuid4()

        async def slow_rebuild(session, cid, task_id=None):  # type: ignore[no-untyped-def]
            import asyncio

            await asyncio.sleep(10)

        with (
            patch("app.routers.chat.wiki_engine.handle_rebuild", new_callable=AsyncMock) as mock_rb,
            patch("app.routers.chat.async_session_factory") as mock_factory,
        ):
            mock_rb.side_effect = slow_rebuild
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with TestClient(app) as tc, tc.websocket_connect(f"/api/classes/{class_id}/chat") as ws:
                ws.send_json({"type": "message", "content": "/rebuild"})

                first = ws.receive_json()
                assert first["type"] == "progress"
                op_id = first["operation_id"]

                ws.send_json({"type": "cancel", "operation_id": op_id})

                while True:
                    msg = ws.receive_json()
                    if msg["type"] in ("error", "complete"):
                        break


class TestGracefulDegradationIntegration:
    """Verify LLM-dependent endpoints return 503 while independent ones work."""

    @pytest.fixture
    async def client_no_llm_override(
        self,
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

    async def _reset_llm_cache(self) -> None:
        import app.dependencies as deps

        deps._cache_result = None
        deps._cache_time = 0.0

    async def test_independent_endpoints_work_when_llm_down(
        self, client_no_llm_override: AsyncClient
    ) -> None:
        await self._reset_llm_cache()

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(side_effect=RuntimeError("LLM down"))

        with patch("app.dependencies.get_llm_provider", return_value=mock_provider):
            assert (await client_no_llm_override.get("/health")).status_code == 200
            assert (await client_no_llm_override.get("/api/classes")).status_code == 200

            class_id = uuid.uuid4()
            resp = await client_no_llm_override.get(f"/api/classes/{class_id}/wiki/tree")
            assert resp.status_code == 200

    async def test_dependent_endpoints_503_when_llm_down(
        self, client_no_llm_override: AsyncClient
    ) -> None:
        await self._reset_llm_cache()

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(side_effect=RuntimeError("LLM down"))

        class_id = uuid.uuid4()
        with patch("app.dependencies.get_llm_provider", return_value=mock_provider):
            lint_resp = await client_no_llm_override.post(f"/api/classes/{class_id}/wiki/lint")
            assert lint_resp.status_code == 503
            assert lint_resp.json()["code"] == "LLM_UNAVAILABLE"

            await self._reset_llm_cache()
            rebuild_resp = await client_no_llm_override.post(
                f"/api/classes/{class_id}/wiki/rebuild"
            )
            assert rebuild_resp.status_code == 503
            assert rebuild_resp.json()["code"] == "LLM_UNAVAILABLE"
