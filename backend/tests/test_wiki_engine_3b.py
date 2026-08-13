"""Tests for Phase 3B first wave: CRUD, export, index/log (Tasks 3B.1, 3B.6, 3B.7)."""

from __future__ import annotations

import uuid
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db_models import Base, WikiCategory, WikiPage
from app.services.wiki_engine import (
    ExportResult,
    WikiPageContent,
    WikiTreeNode,
    append_log,
    get_wiki_context,
    get_wiki_page,
    get_wiki_tree,
    handle_export,
    rebuild_index,
    update_wiki_page,
)
from app.services.wiki_search import ensure_fts_index


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


def _setup_wiki(tmp_path: Path) -> Path:
    """Create a minimal wiki directory with a page."""
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()
    pages_dir = wiki_path / "pages" / "concepts"
    pages_dir.mkdir(parents=True)
    (pages_dir / "testing.md").write_text(
        '---\ntitle: "Testing"\ntype: concept\nsources: [abc123]\n'
        "tags: [testing, qa]\nuser_edited: false\n---\n\n# Testing\n\nContent about testing.\n",
        encoding="utf-8",
    )
    summaries_dir = wiki_path / "pages" / "source-summaries"
    summaries_dir.mkdir(parents=True)
    (summaries_dir / "lecture-1.md").write_text(
        '---\ntitle: "Lecture 1 Summary"\ntype: source-summary\nsources: [def456]\n'
        "tags: [lecture]\nuser_edited: false\n---\n\n# Lecture 1\n\nSummary content.\n",
        encoding="utf-8",
    )
    (wiki_path / "index.md").write_text("# Wiki Index\n", encoding="utf-8")
    return wiki_path


async def test_get_wiki_tree(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()

    page1 = WikiPage(
        class_id=class_id,
        path="pages/concepts/testing.md",
        title="Testing",
        category=WikiCategory.CONCEPT,
        content='---\ntitle: "Testing"\ntype: concept\nuser_edited: false\n---\nContent.',
        source_file_ids=["abc"],
    )
    page2 = WikiPage(
        class_id=class_id,
        path="pages/source-summaries/lecture.md",
        title="Lecture",
        category=WikiCategory.SOURCE_SUMMARY,
        content='---\ntitle: "Lecture"\ntype: source-summary\nuser_edited: true\n---\nSummary.',
        source_file_ids=["def"],
    )
    db_session.add(page1)
    db_session.add(page2)
    await db_session.flush()

    tree = await get_wiki_tree(db_session, class_id)
    assert len(tree) == 2
    assert all(isinstance(n, WikiTreeNode) for n in tree)
    paths = {n.path for n in tree}
    assert "pages/concepts/testing.md" in paths
    assert "pages/source-summaries/lecture.md" in paths
    edited_node = next(n for n in tree if n.path == "pages/source-summaries/lecture.md")
    assert edited_node.user_edited is True


async def test_get_wiki_page(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = _setup_wiki(tmp_path)

    db_page = WikiPage(
        class_id=class_id,
        path="pages/concepts/testing.md",
        title="Testing",
        category=WikiCategory.CONCEPT,
        content="",
        source_file_ids=["abc123"],
    )
    db_session.add(db_page)
    await db_session.flush()

    with patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path):
        result = await get_wiki_page(db_session, class_id, "pages/concepts/testing.md")

    assert result is not None
    assert isinstance(result, WikiPageContent)
    assert result.title == "Testing"
    assert result.category == "concept"
    assert result.user_edited is False
    assert "abc123" in result.source_file_ids


async def test_get_wiki_page_not_found(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()

    with patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path):
        result = await get_wiki_page(db_session, class_id, "pages/nope.md")

    assert result is None


async def test_get_wiki_context(tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()
    (wiki_path / "index.md").write_text("# Index\n- Testing\n", encoding="utf-8")

    with patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path):
        ctx = get_wiki_context(class_id)

    assert "Hypatia Wiki Schema" in ctx
    assert "# Index" in ctx
    assert "- Testing" in ctx


async def test_update_wiki_page(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()

    new_content = (
        '---\ntitle: "New Page"\ntype: concept\nsources: []\n'
        "tags: [new]\nuser_edited: false\n---\n\n# New Page\n\nHello.\n"
    )

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.commit_wiki_change", return_value="sha1"),
    ):
        await update_wiki_page(db_session, class_id, "pages/concepts/new.md", new_content)

    page_file = wiki_path / "pages" / "concepts" / "new.md"
    assert page_file.exists()
    assert page_file.read_text(encoding="utf-8") == new_content

    from sqlalchemy import select

    result = await db_session.execute(select(WikiPage).where(WikiPage.class_id == class_id))
    db_page = result.scalar_one()
    assert db_page.title == "New Page"
    assert db_page.category == WikiCategory.CONCEPT


async def test_update_wiki_page_user_edit(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()

    content = (
        '---\ntitle: "Edited"\ntype: concept\nsources: []\n'
        "tags: []\nuser_edited: false\n---\n\nUser wrote this.\n"
    )

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.commit_wiki_change", return_value="sha2") as mock_commit,
    ):
        await update_wiki_page(
            db_session, class_id, "pages/concepts/edited.md", content, is_user_edit=True
        )

    page_file = wiki_path / "pages" / "concepts" / "edited.md"
    written = page_file.read_text(encoding="utf-8")
    assert "user_edited: true" in written
    mock_commit.assert_called_once()
    assert "user-edit:" in mock_commit.call_args[0][1]


async def test_rebuild_index(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = _setup_wiki(tmp_path)

    page = WikiPage(
        class_id=class_id,
        path="pages/concepts/testing.md",
        title="Testing",
        category=WikiCategory.CONCEPT,
        content="x",
        source_file_ids=["a", "b"],
    )
    db_session.add(page)
    await db_session.flush()

    with patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path):
        index_content = await rebuild_index(db_session, class_id)

    assert "Testing" in index_content
    assert "2 sources" in index_content
    assert "Lecture 1 Summary" in index_content
    index_file = wiki_path / "index.md"
    assert index_file.read_text(encoding="utf-8") == index_content


def test_append_log(tmp_path: Path):
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()

    append_log(wiki_path, "export", "zip (5 pages)")
    log_file = wiki_path / "log.md"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "# Wiki Log" in content
    assert "export | zip (5 pages)" in content

    append_log(wiki_path, "summarize", "gradient descent")
    content = log_file.read_text(encoding="utf-8")
    assert "summarize | gradient descent" in content


async def test_handle_export(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = _setup_wiki(tmp_path)

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.settings") as mock_settings,
    ):
        mock_settings.data_dir = tmp_path / "data"
        result = await handle_export(db_session, class_id)

    assert isinstance(result, ExportResult)
    assert result.success is True
    assert result.page_count == 2
    assert result.export_path is not None

    with zipfile.ZipFile(result.export_path, "r") as zf:
        names = zf.namelist()
        assert "index.md" in names
        assert "pages/concepts/testing.md" in names
        assert "pages/source-summaries/lecture-1.md" in names


async def test_handle_export_empty_wiki(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()

    with patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path):
        result = await handle_export(db_session, class_id)

    assert result.success is False
    assert "No wiki pages" in (result.error or "")
