"""Tests for Wiki router (Task 4.4)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import get_session
from app.dependencies import check_llm_available
from app.main import app
from app.models.db_models import Base, WikiCategory, WikiPage


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


@pytest.fixture
async def class_with_pages(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, list[WikiPage]]:
    class_id = uuid.uuid4()
    async with session_factory() as session:
        pages = [
            WikiPage(
                class_id=class_id,
                path="index.md",
                title="Index",
                category=WikiCategory.INDEX,
                content="# Welcome\n\nThis is the index.",
                source_file_ids=[],
            ),
            WikiPage(
                class_id=class_id,
                path="concepts/gravity.md",
                title="Gravity",
                category=WikiCategory.CONCEPT,
                content="# Gravity\n\nForce of attraction.",
                source_file_ids=["file-1"],
            ),
        ]
        session.add_all(pages)
        await session.commit()
        for p in pages:
            await session.refresh(p)
    return class_id, pages


class TestWikiTree:
    async def test_returns_tree_nodes(
        self, client: AsyncClient, class_with_pages: tuple[uuid.UUID, list[WikiPage]]
    ) -> None:
        class_id, _ = class_with_pages
        with patch("app.routers.wiki.wiki_engine.get_wiki_tree", new_callable=AsyncMock) as mock:
            from app.services.wiki_engine import WikiTreeNode

            mock.return_value = [
                WikiTreeNode(path="index.md", title="Index", category="index", user_edited=False),
                WikiTreeNode(
                    path="concepts/gravity.md",
                    title="Gravity",
                    category="concept",
                    user_edited=False,
                ),
            ]
            resp = await client.get(f"/api/classes/{class_id}/wiki/tree")
            assert resp.status_code == 200
            body = resp.json()
            assert len(body) == 2
            assert body[0]["path"] == "index.md"


class TestWikiIndex:
    async def test_returns_index_content(
        self, client: AsyncClient, class_with_pages: tuple[uuid.UUID, list[WikiPage]]
    ) -> None:
        class_id, _pages = class_with_pages
        with patch("app.routers.wiki.wiki_engine.get_wiki_page", new_callable=AsyncMock) as mock:
            mock.return_value = type("Obj", (), {"content": "# Welcome"})()
            resp = await client.get(f"/api/classes/{class_id}/wiki/index")
            assert resp.status_code == 200
            assert resp.json()["content"] == "# Welcome"

    async def test_returns_empty_when_no_index(self, client: AsyncClient) -> None:
        class_id = uuid.uuid4()
        with patch("app.routers.wiki.wiki_engine.get_wiki_page", new_callable=AsyncMock) as mock:
            mock.return_value = None
            resp = await client.get(f"/api/classes/{class_id}/wiki/index")
            assert resp.status_code == 200
            assert resp.json()["content"] == ""


class TestGetWikiPage:
    async def test_returns_page(
        self, client: AsyncClient, class_with_pages: tuple[uuid.UUID, list[WikiPage]]
    ) -> None:
        class_id, _pages = class_with_pages
        resp = await client.get(f"/api/classes/{class_id}/wiki/pages/concepts/gravity.md")
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "Gravity"
        assert "Gravity" in body["content"]

    async def test_not_found(self, client: AsyncClient) -> None:
        class_id = uuid.uuid4()
        resp = await client.get(f"/api/classes/{class_id}/wiki/pages/nonexistent.md")
        assert resp.status_code == 404


class TestUpdateWikiPage:
    async def test_updates_page(
        self, client: AsyncClient, class_with_pages: tuple[uuid.UUID, list[WikiPage]]
    ) -> None:
        class_id, _pages = class_with_pages
        with patch(
            "app.routers.wiki.wiki_engine.update_wiki_page", new_callable=AsyncMock
        ) as mock_update:
            mock_update.return_value = None
            resp = await client.put(
                f"/api/classes/{class_id}/wiki/pages/concepts/gravity.md",
                json={"content": "# Gravity\n\nUpdated content."},
            )
            assert resp.status_code == 200
            mock_update.assert_called_once()


class TestWikiSearch:
    async def test_returns_search_results(
        self, client: AsyncClient, class_with_pages: tuple[uuid.UUID, list[WikiPage]]
    ) -> None:
        class_id, _ = class_with_pages
        with patch("app.routers.wiki.search_wiki_pages", new_callable=AsyncMock) as mock_search:

            @dataclass
            class FakeResult:
                path: str = "concepts/gravity.md"
                title: str = "Gravity"
                snippet: str = "Force of attraction"
                rank: float = 1.0

            mock_search.return_value = [FakeResult()]
            resp = await client.get(f"/api/classes/{class_id}/wiki/search?q=gravity")
            assert resp.status_code == 200
            body = resp.json()
            assert len(body) == 1
            assert body[0]["title"] == "Gravity"

    async def test_empty_query_rejected(self, client: AsyncClient) -> None:
        class_id = uuid.uuid4()
        resp = await client.get(f"/api/classes/{class_id}/wiki/search?q=")
        assert resp.status_code == 422


class TestWikiExport:
    async def test_export_returns_zip(self, client: AsyncClient, tmp_path: Path) -> None:
        class_id = uuid.uuid4()
        zip_path = tmp_path / "export.zip"
        zip_path.write_bytes(b"PK\x03\x04fake")

        with patch(
            "app.routers.wiki.wiki_engine.handle_export", new_callable=AsyncMock
        ) as mock_export:
            from app.services.wiki_engine import ExportResult

            mock_export.return_value = ExportResult(
                success=True, export_path=str(zip_path), page_count=5
            )
            resp = await client.post(f"/api/classes/{class_id}/wiki/export")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/zip"


class TestWikiLint:
    async def test_lint_returns_issues(self, client: AsyncClient) -> None:
        class_id = uuid.uuid4()
        with patch("app.routers.wiki.wiki_engine.handle_lint", new_callable=AsyncMock) as mock_lint:
            from app.services.wiki_engine import LintIssue, LintResult

            mock_lint.return_value = LintResult(
                success=True,
                issues=[
                    LintIssue(
                        severity="warning",
                        issue_type="dead_link",
                        page="index.md",
                        description="Broken link to missing.md",
                    )
                ],
            )
            resp = await client.post(f"/api/classes/{class_id}/wiki/lint")
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert len(body["issues"]) == 1


class TestWikiRebuild:
    async def test_rebuild_preview(self, client: AsyncClient) -> None:
        class_id = uuid.uuid4()
        with patch(
            "app.routers.wiki.wiki_engine.handle_rebuild_preview", new_callable=AsyncMock
        ) as mock:
            from app.services.wiki_engine import RebuildPreview

            mock.return_value = RebuildPreview(
                pages_to_create=["a.md"],
                pages_to_delete=["b.md"],
                pages_preserved_user_edited=["c.md"],
                source_file_count=3,
                estimated_tokens=5000,
            )
            resp = await client.post(f"/api/classes/{class_id}/wiki/rebuild?confirm=false")
            assert resp.status_code == 200
            body = resp.json()
            assert body["pages_to_create"] == ["a.md"]
            assert body["estimated_tokens"] == 5000

    async def test_rebuild_confirmed_starts_task(self, client: AsyncClient) -> None:
        class_id = uuid.uuid4()
        resp = await client.post(f"/api/classes/{class_id}/wiki/rebuild?confirm=true")
        assert resp.status_code == 200
        body = resp.json()
        assert "task_id" in body
        assert body["status"] == "started"
