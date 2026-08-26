"""Tests for hybrid search (Phase 7, Task 7.3)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.wiki_search import (
    WikiSearchResult,
    ensure_fts_index,
    hybrid_search,
    sync_fts_page,
)


@pytest.fixture
async def search_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await ensure_fts_index(engine)
    async with engine.begin() as conn:
        await conn.execute(
            text("""
                CREATE TABLE IF NOT EXISTS wiki_pages (
                    id TEXT PRIMARY KEY,
                    class_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'concept',
                    content TEXT NOT NULL DEFAULT '',
                    source_file_ids TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _sync_page(
    session: AsyncSession,
    page_id: uuid.UUID,
    class_id: uuid.UUID,
    path: str,
    title: str,
    content: str,
    category: str = "concept",
) -> None:
    pid_hex = page_id.hex
    cid_hex = class_id.hex
    await session.execute(
        text("""
            INSERT OR REPLACE INTO wiki_pages (id, class_id, path, title, category, content)
            VALUES (:id, :cid, :path, :title, :category, :content)
        """),
        {
            "id": pid_hex,
            "cid": cid_hex,
            "path": path,
            "title": title,
            "category": category,
            "content": content,
        },
    )
    await sync_fts_page(session, page_id, class_id, path, title, content)


async def test_hybrid_keyword_mode(search_session: AsyncSession):
    class_id = uuid.uuid4()
    await _sync_page(search_session, uuid.uuid4(), class_id, "a.md", "Alpha", "algorithms and data")
    await search_session.commit()

    results = await hybrid_search(search_session, class_id, "algorithms", mode="keyword")
    assert len(results) == 1
    assert results[0].title == "Alpha"


async def test_hybrid_semantic_mode_fallback(search_session: AsyncSession):
    """When embeddings are unavailable, semantic mode returns empty."""
    class_id = uuid.uuid4()
    await _sync_page(search_session, uuid.uuid4(), class_id, "a.md", "Alpha", "test content")
    await search_session.commit()

    with patch(
        "app.services.wiki_search._get_semantic_results", new_callable=AsyncMock
    ) as mock_sem:
        mock_sem.return_value = []
        results = await hybrid_search(search_session, class_id, "test", mode="semantic")
        assert results == []


async def test_hybrid_mode_fuses_results(search_session: AsyncSession):
    """Hybrid mode combines keyword and semantic results via RRF."""
    class_id = uuid.uuid4()
    pid1 = uuid.uuid4()
    pid2 = uuid.uuid4()
    pid3 = uuid.uuid4()

    await _sync_page(search_session, pid1, class_id, "a.md", "Alpha", "machine learning")
    await _sync_page(search_session, pid2, class_id, "b.md", "Beta", "deep learning neural")
    await _sync_page(search_session, pid3, class_id, "c.md", "Gamma", "biology cells")
    await search_session.commit()

    # Mock semantic results that bring pid3 to the top
    semantic_results = [
        WikiSearchResult(
            page_id=pid3.hex,
            class_id=class_id.hex,
            path="c.md",
            title="Gamma",
            rank=0.95,
            snippet="",
            category="concept",
        ),
        WikiSearchResult(
            page_id=pid1.hex,
            class_id=class_id.hex,
            path="a.md",
            title="Alpha",
            rank=0.80,
            snippet="",
            category="concept",
        ),
    ]

    with patch(
        "app.services.wiki_search._get_semantic_results", new_callable=AsyncMock
    ) as mock_sem:
        mock_sem.return_value = semantic_results
        results = await hybrid_search(search_session, class_id, "machine learning", mode="hybrid")

    # pid1 appears in both keyword and semantic → highest fused score
    assert len(results) >= 1
    page_ids = [r.page_id for r in results]
    assert pid1.hex in page_ids


async def test_hybrid_fallback_when_no_embeddings(search_session: AsyncSession):
    """Hybrid gracefully falls back to keyword-only when semantic fails."""
    class_id = uuid.uuid4()
    await _sync_page(search_session, uuid.uuid4(), class_id, "a.md", "Alpha", "quantum physics")
    await search_session.commit()

    with patch(
        "app.services.wiki_search._get_semantic_results", new_callable=AsyncMock
    ) as mock_sem:
        mock_sem.return_value = []
        results = await hybrid_search(search_session, class_id, "quantum", mode="hybrid")

    assert len(results) == 1
    assert results[0].title == "Alpha"


async def test_hybrid_category_filter(search_session: AsyncSession):
    class_id = uuid.uuid4()
    pid1 = uuid.uuid4()
    pid2 = uuid.uuid4()

    await _sync_page(
        search_session, pid1, class_id, "a.md", "Alpha", "data structures", category="concept"
    )
    await _sync_page(
        search_session, pid2, class_id, "b.md", "Beta", "data summary", category="source-summary"
    )
    await search_session.commit()

    # Semantic returns both
    semantic_results = [
        WikiSearchResult(
            page_id=pid2.hex,
            class_id=class_id.hex,
            path="b.md",
            title="Beta",
            rank=0.9,
            snippet="",
            category="source-summary",
        ),
        WikiSearchResult(
            page_id=pid1.hex,
            class_id=class_id.hex,
            path="a.md",
            title="Alpha",
            rank=0.8,
            snippet="",
            category="concept",
        ),
    ]

    with patch(
        "app.services.wiki_search._get_semantic_results", new_callable=AsyncMock
    ) as mock_sem:
        mock_sem.return_value = semantic_results
        results = await hybrid_search(
            search_session, class_id, "data", mode="hybrid", category="concept"
        )

    assert all(r.category == "concept" for r in results)
    assert len(results) == 1


async def test_hybrid_empty_query(search_session: AsyncSession):
    results = await hybrid_search(search_session, uuid.uuid4(), "", mode="hybrid")
    assert results == []
