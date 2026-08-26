"""Tests for FTS5 wiki search (Task 3A.6 + Phase 7 category/pagination)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.wiki_search import (
    count_wiki_search_results,
    delete_fts_page,
    ensure_fts_index,
    search_wiki_pages,
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
    tags: list[str] | None = None,
    category: str = "concept",
) -> None:
    """Insert into both wiki_pages and FTS for test purposes."""
    pid_hex = page_id.hex  # 32-char no-dash format matching SQLAlchemy Uuid storage
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
    await sync_fts_page(session, page_id, class_id, path, title, content, tags)


async def test_ensure_fts_index_creates_table(search_session: AsyncSession):
    result = await search_session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='wiki_pages_fts'")
    )
    assert result.fetchone() is not None


async def test_sync_and_search(search_session: AsyncSession):
    class_id = uuid.uuid4()
    page_id = uuid.uuid4()

    await _sync_page(
        search_session,
        page_id=page_id,
        class_id=class_id,
        path="pages/concepts/neural-networks.md",
        title="Neural Networks",
        content="Neural networks are computing systems inspired by biological brains.",
        tags=["machine-learning", "deep-learning"],
    )
    await search_session.commit()

    results = await search_wiki_pages(search_session, class_id, "neural networks")
    assert len(results) == 1
    assert results[0].page_id == str(page_id).replace("-", "")
    assert results[0].title == "Neural Networks"


async def test_search_filters_by_class(search_session: AsyncSession):
    class_a = uuid.uuid4()
    class_b = uuid.uuid4()

    await _sync_page(
        search_session,
        page_id=uuid.uuid4(),
        class_id=class_a,
        path="pages/concepts/x.md",
        title="Concept X",
        content="Some content about topic X",
    )
    await _sync_page(
        search_session,
        page_id=uuid.uuid4(),
        class_id=class_b,
        path="pages/concepts/y.md",
        title="Concept Y",
        content="Some content about topic X also",
    )
    await search_session.commit()

    results = await search_wiki_pages(search_session, class_a, "topic")
    assert len(results) == 1
    assert results[0].title == "Concept X"


async def test_delete_fts_page(search_session: AsyncSession):
    class_id = uuid.uuid4()
    page_id = uuid.uuid4()

    await _sync_page(
        search_session,
        page_id=page_id,
        class_id=class_id,
        path="pages/concepts/delete-me.md",
        title="Delete Me",
        content="This page will be deleted.",
    )
    await search_session.commit()

    await delete_fts_page(search_session, page_id)
    await search_session.commit()

    results = await search_wiki_pages(search_session, class_id, "deleted")
    assert results == []


async def test_search_empty_query(search_session: AsyncSession):
    results = await search_wiki_pages(search_session, uuid.uuid4(), "")
    assert results == []


async def test_search_no_results(search_session: AsyncSession):
    results = await search_wiki_pages(search_session, uuid.uuid4(), "nonexistent")
    assert results == []


async def test_sync_updates_existing(search_session: AsyncSession):
    class_id = uuid.uuid4()
    page_id = uuid.uuid4()

    await _sync_page(
        search_session,
        page_id=page_id,
        class_id=class_id,
        path="pages/concepts/evolving.md",
        title="Evolving",
        content="Original content about biology",
    )
    await search_session.commit()

    await _sync_page(
        search_session,
        page_id=page_id,
        class_id=class_id,
        path="pages/concepts/evolving.md",
        title="Evolving",
        content="Updated content about chemistry",
    )
    await search_session.commit()

    bio_results = await search_wiki_pages(search_session, class_id, "biology")
    assert bio_results == []

    chem_results = await search_wiki_pages(search_session, class_id, "chemistry")
    assert len(chem_results) == 1


# --- Phase 7: Category filtering and pagination tests ---


async def test_search_returns_category(search_session: AsyncSession):
    class_id = uuid.uuid4()

    await _sync_page(
        search_session,
        uuid.uuid4(),
        class_id,
        "pages/concepts/ml.md",
        "Machine Learning",
        "Machine learning is a subset of AI.",
        category="concept",
    )
    await search_session.commit()

    results = await search_wiki_pages(search_session, class_id, "machine learning")
    assert len(results) == 1
    assert results[0].category == "concept"


async def test_search_category_filter(search_session: AsyncSession):
    class_id = uuid.uuid4()

    await _sync_page(
        search_session,
        uuid.uuid4(),
        class_id,
        "pages/concepts/ai.md",
        "AI Concepts",
        "Artificial intelligence overview.",
        category="concept",
    )
    await _sync_page(
        search_session,
        uuid.uuid4(),
        class_id,
        "pages/sources/ai-lecture.md",
        "AI Lecture Notes",
        "Artificial intelligence lecture notes from class.",
        category="source-summary",
    )
    await search_session.commit()

    all_results = await search_wiki_pages(search_session, class_id, "artificial intelligence")
    assert len(all_results) == 2

    concept_results = await search_wiki_pages(
        search_session, class_id, "artificial intelligence", category="concept"
    )
    assert len(concept_results) == 1
    assert concept_results[0].title == "AI Concepts"

    source_results = await search_wiki_pages(
        search_session, class_id, "artificial intelligence", category="source-summary"
    )
    assert len(source_results) == 1
    assert source_results[0].title == "AI Lecture Notes"


async def test_search_pagination(search_session: AsyncSession):
    class_id = uuid.uuid4()

    for i in range(5):
        await _sync_page(
            search_session,
            uuid.uuid4(),
            class_id,
            f"pages/concepts/topic-{i}.md",
            f"Topic {i}",
            f"Content about algorithms topic number {i}.",
            category="concept",
        )
    await search_session.commit()

    page1 = await search_wiki_pages(search_session, class_id, "algorithms", limit=2, offset=0)
    assert len(page1) == 2

    page2 = await search_wiki_pages(search_session, class_id, "algorithms", limit=2, offset=2)
    assert len(page2) == 2

    page3 = await search_wiki_pages(search_session, class_id, "algorithms", limit=2, offset=4)
    assert len(page3) == 1


async def test_count_wiki_search_results(search_session: AsyncSession):
    class_id = uuid.uuid4()

    for i in range(5):
        await _sync_page(
            search_session,
            uuid.uuid4(),
            class_id,
            f"pages/concepts/count-{i}.md",
            f"Count {i}",
            f"Counting topic data {i}.",
            category="concept",
        )
    await _sync_page(
        search_session,
        uuid.uuid4(),
        class_id,
        "pages/sources/count-source.md",
        "Count Source",
        "Counting topic source material.",
        category="source-summary",
    )
    await search_session.commit()

    total = await count_wiki_search_results(search_session, class_id, "counting")
    assert total == 6

    concept_count = await count_wiki_search_results(
        search_session, class_id, "counting", category="concept"
    )
    assert concept_count == 5
