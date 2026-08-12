"""Tests for FTS5 wiki search (Task 3A.6)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.wiki_search import (
    delete_fts_page,
    ensure_fts_index,
    search_wiki_pages,
    sync_fts_page,
)


@pytest.fixture
async def search_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await ensure_fts_index(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def test_ensure_fts_index_creates_table(search_session: AsyncSession):
    from sqlalchemy import text

    result = await search_session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='wiki_pages_fts'")
    )
    assert result.fetchone() is not None


async def test_sync_and_search(search_session: AsyncSession):
    class_id = uuid.uuid4()
    page_id = uuid.uuid4()

    await sync_fts_page(
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
    assert results[0].page_id == str(page_id)
    assert results[0].title == "Neural Networks"


async def test_search_filters_by_class(search_session: AsyncSession):
    class_a = uuid.uuid4()
    class_b = uuid.uuid4()

    await sync_fts_page(
        search_session,
        page_id=uuid.uuid4(),
        class_id=class_a,
        path="pages/concepts/x.md",
        title="Concept X",
        content="Some content about topic X",
    )
    await sync_fts_page(
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

    await sync_fts_page(
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

    await sync_fts_page(
        search_session,
        page_id=page_id,
        class_id=class_id,
        path="pages/concepts/evolving.md",
        title="Evolving",
        content="Original content about biology",
    )
    await search_session.commit()

    await sync_fts_page(
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
