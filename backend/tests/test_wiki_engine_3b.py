"""Tests for Phase 3B first wave: CRUD, export, index/log (Tasks 3B.1, 3B.6, 3B.7)."""

from __future__ import annotations

import uuid
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db_models import Base, WikiCategory, WikiPage
from app.services.wiki_engine import (
    ExportResult,
    WikiPageContent,
    WikiTreeNode,
    get_wiki_context,
    get_wiki_page,
    get_wiki_tree,
    handle_export,
    update_wiki_page,
)
from app.services.wiki_git import wiki_dir
from app.services.wiki_search import ensure_fts_index
from app.services.wiki_store import append_log, load_index

TESTING_PAGE = (
    '---\ntitle: "Testing"\ntype: concept\nsources: [abc123]\n'
    "tags: [testing, qa]\nuser_edited: false\n---\n\n# Testing\n\nContent about testing.\n"
)
LECTURE_PAGE = (
    '---\ntitle: "Lecture 1 Summary"\ntype: source-summary\nsources: [def456]\n'
    "tags: [lecture]\nuser_edited: false\n---\n\n# Lecture 1\n\nSummary content.\n"
)


@pytest.fixture
async def db_session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_fts_index(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _add_wiki(session: AsyncSession, class_id: uuid.UUID) -> None:
    session.add_all(
        [
            WikiPage(
                class_id=class_id,
                path="pages/concepts/testing.md",
                title="Testing",
                category=WikiCategory.CONCEPT,
                content=TESTING_PAGE,
                source_file_ids=["abc123", "xyz789"],
            ),
            WikiPage(
                class_id=class_id,
                path="pages/source-summaries/lecture-1.md",
                title="Lecture 1 Summary",
                category=WikiCategory.SOURCE_SUMMARY,
                content=LECTURE_PAGE,
                source_file_ids=["def456"],
            ),
        ]
    )
    await session.flush()


async def test_get_wiki_tree(db_session: AsyncSession):
    class_id = uuid.uuid4()
    db_session.add_all(
        [
            WikiPage(
                class_id=class_id,
                path="pages/concepts/testing.md",
                title="Testing",
                category=WikiCategory.CONCEPT,
                content="Content.",
                source_file_ids=["abc"],
            ),
            WikiPage(
                class_id=class_id,
                path="pages/source-summaries/lecture.md",
                title="Lecture",
                category=WikiCategory.SOURCE_SUMMARY,
                content="Summary.",
                source_file_ids=["def"],
                user_edited=True,
            ),
        ]
    )
    await db_session.flush()

    tree = await get_wiki_tree(db_session, class_id)
    assert len(tree) == 2
    assert all(isinstance(n, WikiTreeNode) for n in tree)
    edited = {n.path: n.user_edited for n in tree}
    assert edited == {
        "pages/concepts/testing.md": False,
        "pages/source-summaries/lecture.md": True,
    }


async def test_get_wiki_page_reads_the_database(db_session: AsyncSession):
    class_id = uuid.uuid4()
    await _add_wiki(db_session, class_id)

    result = await get_wiki_page(db_session, class_id, "pages/concepts/testing.md")

    assert isinstance(result, WikiPageContent)
    assert result.title == "Testing"
    assert result.category == "concept"
    assert result.content == TESTING_PAGE
    assert result.user_edited is False
    assert "abc123" in result.source_file_ids


async def test_get_wiki_page_index_is_generated(db_session: AsyncSession):
    class_id = uuid.uuid4()
    await _add_wiki(db_session, class_id)

    result = await get_wiki_page(db_session, class_id, "index.md")

    assert result is not None
    assert "[Testing](pages/concepts/testing.md) (2 sources)" in result.content


async def test_get_wiki_page_not_found(db_session: AsyncSession):
    assert await get_wiki_page(db_session, uuid.uuid4(), "pages/nope.md") is None


async def test_get_wiki_context(db_session: AsyncSession):
    class_id = uuid.uuid4()
    await _add_wiki(db_session, class_id)

    ctx = await get_wiki_context(db_session, class_id)

    assert "Hypatia Wiki Schema" in ctx
    assert "# Wiki Index" in ctx
    assert "Lecture 1 Summary" in ctx


async def test_update_wiki_page_stores_and_mirrors(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    new_content = (
        '---\ntitle: "New Page"\ntype: concept\nsources: []\n'
        "tags: [new]\nuser_edited: false\n---\n\n# New Page\n\nHello.\n"
    )

    with (
        patch("app.services.wiki_store.init_wiki_repo", return_value=wiki_path),
        patch("app.services.wiki_store.commit_wiki_change", return_value="sha1"),
    ):
        await update_wiki_page(db_session, class_id, "pages/concepts/new.md", new_content)

    db_page = (
        await db_session.execute(select(WikiPage).where(WikiPage.class_id == class_id))
    ).scalar_one()
    assert db_page.title == "New Page"
    assert db_page.category == WikiCategory.CONCEPT
    assert db_page.content == new_content
    page_file = wiki_path / "pages" / "concepts" / "new.md"
    assert page_file.read_text(encoding="utf-8") == new_content
    assert "New Page" in (wiki_path / "index.md").read_text(encoding="utf-8")


async def test_update_wiki_page_user_edit(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    content = (
        '---\ntitle: "Edited"\ntype: concept\nsources: []\n'
        "tags: []\nuser_edited: false\n---\n\nUser wrote this.\n"
    )

    with (
        patch("app.services.wiki_store.init_wiki_repo", return_value=tmp_path / "wiki"),
        patch("app.services.wiki_store.commit_wiki_change", return_value="sha2") as mock_commit,
    ):
        await update_wiki_page(
            db_session, class_id, "pages/concepts/edited.md", content, is_user_edit=True
        )

    db_page = (
        await db_session.execute(select(WikiPage).where(WikiPage.class_id == class_id))
    ).scalar_one()
    assert db_page.user_edited is True
    assert "user_edited: true" in db_page.content
    mock_commit.assert_called_once()
    assert "user-edit:" in mock_commit.call_args[0][1]


async def test_load_index_counts_sources(db_session: AsyncSession):
    class_id = uuid.uuid4()
    await _add_wiki(db_session, class_id)

    index_content = await load_index(db_session, class_id)

    assert "Testing" in index_content
    assert "2 sources" in index_content
    assert "Lecture 1 Summary" in index_content


def test_append_log():
    class_id = uuid.uuid4()

    append_log(class_id, "export", "zip (5 pages)")
    log_file = wiki_dir(str(class_id)) / "log.md"
    content = log_file.read_text(encoding="utf-8")
    assert "# Wiki Log" in content
    assert "export | zip (5 pages)" in content

    append_log(class_id, "summarize", "gradient descent")
    content = log_file.read_text(encoding="utf-8")
    assert content.count("# Wiki Log") == 1
    assert "summarize | gradient descent" in content


async def test_handle_export(db_session: AsyncSession):
    class_id = uuid.uuid4()
    await _add_wiki(db_session, class_id)

    result = await handle_export(db_session, class_id)

    assert isinstance(result, ExportResult)
    assert result.success is True
    assert result.page_count == 2
    assert result.export_path is not None
    with zipfile.ZipFile(result.export_path, "r") as zf:
        assert sorted(zf.namelist()) == [
            "index.md",
            "pages/concepts/testing.md",
            "pages/source-summaries/lecture-1.md",
        ]
        assert zf.read("pages/concepts/testing.md").decode() == TESTING_PAGE


async def test_handle_export_empty_wiki(db_session: AsyncSession):
    result = await handle_export(db_session, uuid.uuid4())

    assert result.success is False
    assert "No wiki pages" in (result.error or "")
