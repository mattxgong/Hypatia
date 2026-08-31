"""Tests for task status REST endpoints (Task 4.7)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import get_session
from app.main import app
from app.models.db_models import Base
from app.services.task_manager import task_manager


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


CLASS_ID = "00000000-0000-0000-0000-000000000001"


class TestTasksRouter:
    def setup_method(self) -> None:
        task_manager._tasks.clear()

    async def test_list_tasks_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/api/tasks")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_tasks_with_task(self, client: AsyncClient) -> None:
        task_id = task_manager.start_task("rebuild", CLASS_ID)
        resp = await client.get("/api/tasks")
        assert resp.status_code == 200
        tasks = resp.json()
        assert len(tasks) == 1
        assert tasks[0]["task_id"] == task_id
        assert tasks[0]["operation"] == "rebuild"
        assert tasks[0]["status"] == "running"
        assert tasks[0]["progress"] == 0

    async def test_list_tasks_filter_by_class(self, client: AsyncClient) -> None:
        task_manager.start_task("rebuild", CLASS_ID)
        task_manager.start_task("lint", "other-class")
        resp = await client.get("/api/tasks", params={"class_id": CLASS_ID})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_get_task(self, client: AsyncClient) -> None:
        task_id = task_manager.start_task("lint", CLASS_ID)
        resp = await client.get(f"/api/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["task_id"] == task_id

    async def test_get_task_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/tasks/nonexistent")
        assert resp.status_code == 404

    async def test_cancel_task(self, client: AsyncClient) -> None:
        task_id = task_manager.start_task("rebuild", CLASS_ID)
        resp = await client.post(f"/api/tasks/{task_id}/cancel")
        assert resp.status_code == 202
        assert task_manager.is_cancelled(task_id)

    async def test_cancel_nonexistent_task(self, client: AsyncClient) -> None:
        resp = await client.post("/api/tasks/nonexistent/cancel")
        assert resp.status_code == 404
