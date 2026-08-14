"""Tests for Classes router and error middleware (Tasks 4.1, 4.2)."""

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


class TestCORSMiddleware:
    async def test_cors_headers_present(self, client: AsyncClient) -> None:
        resp = await client.get("/health", headers={"Origin": "http://localhost:3000"})
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers


class TestErrorHandling:
    async def test_404_returns_structured_json(self, client: AsyncClient) -> None:
        resp = await client.get("/api/classes/00000000-0000-0000-0000-000000000001")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body
        assert "code" in body


class TestClassesRouter:
    async def test_create_class(self, client: AsyncClient, tmp_path: Path) -> None:
        resp = await client.post("/api/classes", json={"name": "Biology 101"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Biology 101"
        assert "id" in body

        class_dir = tmp_path / "classes" / body["id"]
        assert (class_dir / "raw").exists()
        assert (class_dir / "converted").exists()
        assert (class_dir / "wiki").exists()

    async def test_list_classes(self, client: AsyncClient) -> None:
        await client.post("/api/classes", json={"name": "Class A"})
        await client.post("/api/classes", json={"name": "Class B"})
        resp = await client.get("/api/classes")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_get_class_with_stats(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/classes", json={"name": "Stats Class"})
        class_id = create_resp.json()["id"]
        resp = await client.get(f"/api/classes/{class_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["file_count"] == 0
        assert body["page_count"] == 0

    async def test_get_class_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/classes/00000000-0000-0000-0000-000000000001")
        assert resp.status_code == 404

    async def test_update_class(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/classes", json={"name": "Old Name"})
        class_id = create_resp.json()["id"]
        resp = await client.put(f"/api/classes/{class_id}", json={"name": "New Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    async def test_delete_class(self, client: AsyncClient, tmp_path: Path) -> None:
        create_resp = await client.post("/api/classes", json={"name": "To Delete"})
        class_id = create_resp.json()["id"]
        class_dir = tmp_path / "classes" / class_id
        assert class_dir.exists()

        resp = await client.delete(f"/api/classes/{class_id}")
        assert resp.status_code == 204
        assert not class_dir.exists()

        resp = await client.get(f"/api/classes/{class_id}")
        assert resp.status_code == 404
