"""Tests for LLM graceful degradation dependency (Task 4.9)."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import get_session
from app.dependencies import check_llm_available
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


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    """Reset the LLM availability cache between tests."""
    import app.dependencies as deps

    deps._cache_result = None
    deps._cache_time = 0.0


class TestLLMDependency:
    async def test_llm_available_passes(self) -> None:
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value="ok")

        with patch("app.dependencies.get_llm_provider", return_value=mock_provider):
            await check_llm_available()

    async def test_llm_unavailable_raises(self) -> None:
        from app.exceptions import LLMUnavailableError

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(side_effect=RuntimeError("no LLM"))

        with (
            patch("app.dependencies.get_llm_provider", return_value=mock_provider),
            pytest.raises(LLMUnavailableError),
        ):
            await check_llm_available()

    async def test_cache_reuses_result(self) -> None:
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value="ok")

        with patch("app.dependencies.get_llm_provider", return_value=mock_provider):
            await check_llm_available()
            await check_llm_available()

        assert mock_provider.complete.call_count == 1

    async def test_cache_expires(self) -> None:
        import app.dependencies as deps

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value="ok")

        with patch("app.dependencies.get_llm_provider", return_value=mock_provider):
            await check_llm_available()

        deps._cache_time = time.monotonic() - 60

        with patch("app.dependencies.get_llm_provider", return_value=mock_provider):
            await check_llm_available()

        assert mock_provider.complete.call_count == 2


class TestGracefulDegradation:
    async def test_lint_returns_503_when_llm_unavailable(self, client: AsyncClient) -> None:
        app.dependency_overrides.pop(check_llm_available, None)

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(side_effect=RuntimeError("down"))

        class_id = uuid.uuid4()
        with patch("app.dependencies.get_llm_provider", return_value=mock_provider):
            resp = await client.post(f"/api/classes/{class_id}/wiki/lint")

        assert resp.status_code == 503
        assert resp.json()["code"] == "LLM_UNAVAILABLE"

    async def test_rebuild_returns_503_when_llm_unavailable(self, client: AsyncClient) -> None:
        app.dependency_overrides.pop(check_llm_available, None)

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(side_effect=RuntimeError("down"))

        class_id = uuid.uuid4()
        with patch("app.dependencies.get_llm_provider", return_value=mock_provider):
            resp = await client.post(f"/api/classes/{class_id}/wiki/rebuild")

        assert resp.status_code == 503
        assert resp.json()["code"] == "LLM_UNAVAILABLE"

    async def test_non_llm_endpoints_still_work(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
