"""Tests for Phase 3B second wave: /summarize, /remove, /lint, /rebuild, streaming (3B.2-5, 3B.13)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db_models import Base, Class, File, FileStatus, FileType, WikiCategory, WikiPage
from app.services.wiki_engine import (
    LintResult,
    RebuildPreview,
    RebuildResult,
    RemoveResult,
    SummarizeResult,
    _chunk_source,
    _clean_dead_links,
    handle_ask_stream,
    handle_lint,
    handle_rebuild,
    handle_rebuild_preview,
    handle_remove,
    handle_summarize,
)
from app.services.wiki_search import ensure_fts_index
from tests.conftest import StubIngestionQueue


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


def _setup_wiki_with_pages(tmp_path: Path) -> Path:
    """Create a wiki directory with pages and links for testing."""
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()
    pages_dir = wiki_path / "pages" / "concepts"
    pages_dir.mkdir(parents=True)
    summaries_dir = wiki_path / "pages" / "source-summaries"
    summaries_dir.mkdir(parents=True)

    (pages_dir / "testing.md").write_text(
        '---\ntitle: "Testing"\ntype: concept\nsources: []\n'
        "tags: [testing]\nuser_edited: false\n---\n\n"
        "# Testing\n\nTesting is important. See also [[debugging]].\n",
        encoding="utf-8",
    )
    (pages_dir / "debugging.md").write_text(
        '---\ntitle: "Debugging"\ntype: concept\nsources: []\n'
        "tags: [debugging]\nuser_edited: false\n---\n\n"
        "# Debugging\n\nDebugging techniques. See [[testing]].\n",
        encoding="utf-8",
    )
    (summaries_dir / "lecture-1.md").write_text(
        '---\ntitle: "Lecture 1"\ntype: source-summary\nsources: [file1]\n'
        "tags: [lecture]\nuser_edited: false\n---\n\n"
        "# Lecture 1\n\nSummary of lecture 1.\n"
        "Citation: hypatia://cite?file=lecture1.pdf&page=1\n",
        encoding="utf-8",
    )
    (wiki_path / "index.md").write_text("# Index\n- Testing\n- Debugging\n", encoding="utf-8")
    (wiki_path / "log.md").write_text("# Wiki Log\n", encoding="utf-8")
    return wiki_path


# ---------------------------------------------------------------------------
# /summarize tests
# ---------------------------------------------------------------------------


async def test_handle_summarize_no_pages(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()

    with patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path):
        result = await handle_summarize(db_session, class_id, "quantum physics")

    assert isinstance(result, SummarizeResult)
    assert result.success is False
    assert "No wiki pages" in (result.error or "")


async def test_handle_summarize_success(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = _setup_wiki_with_pages(tmp_path)

    page = WikiPage(
        class_id=class_id,
        path="pages/concepts/testing.md",
        title="Testing",
        category=WikiCategory.CONCEPT,
        content="Content about testing.",
        source_file_ids=[],
    )
    db_session.add(page)
    await db_session.flush()

    from app.services.wiki_search import sync_fts_page

    await sync_fts_page(
        db_session,
        page_id=page.id,
        class_id=class_id,
        path="pages/concepts/testing.md",
        title="Testing",
        content="Content about testing.",
        tags=["testing"],
    )
    await db_session.commit()

    llm_output = (
        '<wiki-page path="pages/synthesis/testing-summary.md">\n'
        "---\n"
        'title: "Testing Summary"\n'
        "type: synthesis\n"
        "sources: []\n"
        "tags: [testing, summary]\n"
        "---\n\n"
        "# Testing Summary\n\n"
        "A comprehensive summary of testing concepts.\n"
        "</wiki-page>\n"
    )

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value=llm_output)

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.get_llm_provider", return_value=mock_provider),
        patch("app.services.wiki_engine.commit_wiki_change"),
    ):
        result = await handle_summarize(db_session, class_id, "testing")

    assert isinstance(result, SummarizeResult)
    assert result.success is True
    assert result.page_path is not None
    assert "testing" in result.page_path.lower() or "summary" in result.page_path.lower()


# ---------------------------------------------------------------------------
# /remove tests
# ---------------------------------------------------------------------------


async def test_handle_remove_file_not_found(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()

    result = await handle_remove(db_session, class_id, "nonexistent.pdf")

    assert isinstance(result, RemoveResult)
    assert result.success is False
    assert "not found" in (result.error or "").lower()


async def test_handle_remove_success(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()
    pages_dir = wiki_path / "pages" / "source-summaries"
    pages_dir.mkdir(parents=True)
    (wiki_path / "index.md").write_text("# Index\n", encoding="utf-8")
    (wiki_path / "log.md").write_text("# Wiki Log\n", encoding="utf-8")

    raw_path = tmp_path / "raw" / "lecture.pdf"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"fake pdf")

    cls = Class(id=class_id, name="Test Class")
    db_session.add(cls)
    await db_session.flush()

    file_record = File(
        class_id=class_id,
        original_filename="lecture.pdf",
        file_type=FileType.PDF,
        file_size_bytes=100,
        status=FileStatus.READY,
        raw_path=str(raw_path),
        converted_path=None,
    )
    db_session.add(file_record)
    await db_session.flush()
    file_id = str(file_record.id)

    page_file = pages_dir / "lecture.md"
    page_file.write_text("# Lecture Summary\n", encoding="utf-8")

    wiki_page = WikiPage(
        class_id=class_id,
        path="pages/source-summaries/lecture.md",
        title="Lecture Summary",
        category=WikiCategory.SOURCE_SUMMARY,
        content="# Lecture Summary\n",
        source_file_ids=[file_id],
    )
    db_session.add(wiki_page)
    await db_session.flush()

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.commit_wiki_change"),
        patch("app.services.ingestion_queue.get_ingestion_queue") as mock_get_queue,
    ):
        mock_get_queue.return_value.cancel_file = AsyncMock(return_value=True)
        result = await handle_remove(db_session, class_id, "lecture.pdf")

    assert isinstance(result, RemoveResult)
    assert result.success is True
    mock_get_queue.return_value.cancel_file.assert_awaited_once_with(class_id, file_record.id)
    assert "pages/source-summaries/lecture.md" in result.pages_deleted
    assert not raw_path.exists()
    assert not page_file.exists()

    q = await db_session.execute(select(File).where(File.class_id == class_id))
    assert q.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# _clean_dead_links tests
# ---------------------------------------------------------------------------


def test_clean_dead_links(tmp_path: Path):
    wiki_path = tmp_path / "wiki"
    pages_dir = wiki_path / "pages"
    pages_dir.mkdir(parents=True)

    (pages_dir / "survivor.md").write_text(
        "Some text referencing [[deleted-page]] and [[kept-page]].\n",
        encoding="utf-8",
    )

    cleaned = _clean_dead_links(wiki_path, ["pages/deleted-page.md"])
    assert cleaned == 1

    content = (pages_dir / "survivor.md").read_text(encoding="utf-8")
    assert "[[deleted-page]]" not in content
    assert "deleted-page" in content
    assert "[[kept-page]]" in content


def test_clean_dead_links_keeps_display_text(tmp_path: Path):
    wiki_path = tmp_path / "wiki"
    pages_dir = wiki_path / "pages"
    pages_dir.mkdir(parents=True)
    (pages_dir / "survivor.md").write_text("See [[deleted-page|the old page]].\n", encoding="utf-8")

    assert _clean_dead_links(wiki_path, ["pages/deleted-page.md"]) == 1
    assert (pages_dir / "survivor.md").read_text(encoding="utf-8") == "See the old page.\n"


def test_chunk_source_repeats_page_marker_for_mid_page_chunks() -> None:
    source = "**[Page 1]**\n\n" + "\n".join(f"line {i} of page one" for i in range(40))

    chunks = _chunk_source(source, token_budget=60)

    assert len(chunks) > 1
    assert all(chunk.startswith("**[Page 1]**") for chunk in chunks)


def test_clean_dead_links_no_deletions(tmp_path: Path):
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()
    assert _clean_dead_links(wiki_path, []) == 0


# ---------------------------------------------------------------------------
# /lint tests
# ---------------------------------------------------------------------------


async def test_handle_lint_empty_wiki(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()

    with patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path):
        result = await handle_lint(db_session, class_id)

    assert isinstance(result, LintResult)
    assert result.success is True
    assert result.issues == []


async def test_handle_lint_finds_broken_links(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    pages_dir = wiki_path / "pages"
    pages_dir.mkdir(parents=True)
    (wiki_path / "log.md").write_text("# Log\n", encoding="utf-8")

    (pages_dir / "page-a.md").write_text(
        "---\ntitle: A\n---\nSee [[nonexistent]].\n", encoding="utf-8"
    )
    (pages_dir / "page-b.md").write_text(
        "---\ntitle: B\n---\nLinks to [[page-a]].\n", encoding="utf-8"
    )

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value="No issues found.")

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.get_llm_provider", return_value=mock_provider),
    ):
        result = await handle_lint(db_session, class_id)

    assert result.success is True
    broken = [i for i in result.issues if i.issue_type == "broken_link"]
    assert len(broken) == 1
    assert "nonexistent" in broken[0].description


async def test_handle_lint_finds_dead_citations(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    pages_dir = wiki_path / "pages"
    pages_dir.mkdir(parents=True)
    (wiki_path / "log.md").write_text("# Log\n", encoding="utf-8")

    (pages_dir / "page-c.md").write_text(
        "---\ntitle: C\n---\nCitation: hypatia://cite?file=deleted.pdf&page=1\n",
        encoding="utf-8",
    )

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value="")

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.get_llm_provider", return_value=mock_provider),
    ):
        result = await handle_lint(db_session, class_id)

    assert result.success is True
    dead = [i for i in result.issues if i.issue_type == "dead_citation"]
    assert len(dead) == 1
    assert "deleted.pdf" in dead[0].description


# ---------------------------------------------------------------------------
# /rebuild tests
# ---------------------------------------------------------------------------


async def test_handle_rebuild_preview(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    pages_dir = wiki_path / "pages" / "concepts"
    pages_dir.mkdir(parents=True)
    (wiki_path / "index.md").write_text("# Index\n", encoding="utf-8")

    (pages_dir / "user-page.md").write_text(
        "---\ntitle: User Page\nuser_edited: true\n---\nKept.\n", encoding="utf-8"
    )
    (pages_dir / "auto-page.md").write_text(
        "---\ntitle: Auto Page\nuser_edited: false\n---\nGenerated.\n", encoding="utf-8"
    )

    converted_path = tmp_path / "converted" / "notes.md"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_text("Notes content here.", encoding="utf-8")

    cls = Class(id=class_id, name="Test Class Preview")
    db_session.add(cls)
    await db_session.flush()

    file_record = File(
        class_id=class_id,
        original_filename="notes.pdf",
        file_type=FileType.PDF,
        file_size_bytes=500,
        status=FileStatus.READY,
        raw_path=str(tmp_path / "notes.pdf"),
        converted_path=str(converted_path),
    )
    db_session.add(file_record)
    await db_session.flush()

    with patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path):
        preview = await handle_rebuild_preview(db_session, class_id)

    assert isinstance(preview, RebuildPreview)
    assert preview.source_file_count == 1
    assert len(preview.pages_preserved_user_edited) == 1
    assert "user-page" in preview.pages_preserved_user_edited[0]
    assert len(preview.pages_to_delete) == 1
    assert "auto-page" in preview.pages_to_delete[0]
    assert preview.estimated_tokens > 0


async def test_handle_rebuild_preserves_user_edited(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    pages_dir = wiki_path / "pages" / "concepts"
    pages_dir.mkdir(parents=True)
    (wiki_path / "index.md").write_text("# Index\n", encoding="utf-8")
    (wiki_path / "log.md").write_text("# Log\n", encoding="utf-8")

    user_page = pages_dir / "user-kept.md"
    user_page.write_text(
        "---\ntitle: User Kept\nuser_edited: true\n---\nMy notes.\n", encoding="utf-8"
    )
    auto_page = pages_dir / "auto-delete.md"
    auto_page.write_text(
        "---\ntitle: Auto\nuser_edited: false\n---\nGenerated.\n", encoding="utf-8"
    )

    wiki_page = WikiPage(
        class_id=class_id,
        path="pages/concepts/auto-delete.md",
        title="Auto",
        category=WikiCategory.CONCEPT,
        content="Generated.",
        source_file_ids=[],
    )
    db_session.add(wiki_page)
    await db_session.flush()

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.init_wiki_repo", return_value=wiki_path),
        patch("app.services.wiki_engine.commit_wiki_change"),
    ):
        result = await handle_rebuild(db_session, class_id)

    assert isinstance(result, RebuildResult)
    assert result.success is True
    assert result.pages_preserved == 1
    assert result.pages_deleted == 1
    assert user_page.exists()
    assert not auto_page.exists()


async def test_handle_rebuild_includes_file_mid_ingestion(
    db_session: AsyncSession, tmp_path: Path, stub_ingestion_queue: StubIngestionQueue
):
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()
    converted_path = tmp_path / "converted" / "notes.md"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_text("Notes content here.", encoding="utf-8")

    db_session.add(Class(id=class_id, name="Mid-ingest"))
    await db_session.flush()
    file_record = File(
        class_id=class_id,
        original_filename="notes.pdf",
        file_type=FileType.PDF,
        file_size_bytes=500,
        status=FileStatus.PROCESSING,
        raw_path=str(tmp_path / "notes.pdf"),
        converted_path=str(converted_path),
    )
    db_session.add(file_record)
    await db_session.commit()

    llm_output = (
        '<wiki-page path="pages/source-summaries/notes.md">\n'
        '---\ntitle: "Notes"\ntype: source-summary\nsources: []\ntags: []\n---\n\n'
        "# Notes\n\nSummary.\n</wiki-page>\n"
    )
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value=llm_output)

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.init_wiki_repo", return_value=wiki_path),
        patch("app.services.wiki_engine.commit_wiki_change"),
        patch("app.services.wiki_engine.get_llm_provider", return_value=mock_provider),
    ):
        result = await handle_rebuild(db_session, class_id)

    assert result.success is True
    assert result.pages_created == 1
    assert stub_ingestion_queue.cancelled_files == [(class_id, file_record.id)]
    await db_session.refresh(file_record)
    assert file_record.status == FileStatus.READY


async def _rebuild_fixture(
    db_session: AsyncSession, tmp_path: Path
) -> tuple[uuid.UUID, Path, File]:
    """A wiki with one source, a page generated from it, and a synthesis page."""
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    (wiki_path / "pages" / "concept").mkdir(parents=True)
    (wiki_path / "pages" / "synthesis").mkdir(parents=True)
    converted_path = tmp_path / "converted" / "notes.md"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_text("Notes content here.", encoding="utf-8")

    db_session.add(Class(id=class_id, name=f"Rebuild {class_id}"))
    await db_session.flush()
    file_record = File(
        class_id=class_id,
        original_filename="notes.pdf",
        file_type=FileType.PDF,
        file_size_bytes=500,
        status=FileStatus.READY,
        raw_path=str(tmp_path / "notes.pdf"),
        converted_path=str(converted_path),
    )
    db_session.add(file_record)
    await db_session.flush()

    old = '---\ntitle: "Old Concept"\ntype: concept\nuser_edited: false\n---\n\nOld text.\n'
    (wiki_path / "pages" / "concept" / "old-concept.md").write_text(old, encoding="utf-8")
    db_session.add(
        WikiPage(
            class_id=class_id,
            path="pages/concept/old-concept.md",
            title="Old Concept",
            category=WikiCategory.CONCEPT,
            content=old,
            source_file_ids=[str(file_record.id)],
        )
    )
    (wiki_path / "pages" / "synthesis" / "overview.md").write_text(
        '---\ntitle: "Overview"\ntype: synthesis\nuser_edited: false\n---\n\nSummary.\n',
        encoding="utf-8",
    )
    await db_session.commit()
    return class_id, wiki_path, file_record


@contextmanager
def _rebuild_env(wiki_path: Path, provider: AsyncMock) -> Iterator[None]:
    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.init_wiki_repo", return_value=wiki_path),
        patch("app.services.wiki_engine.commit_wiki_change"),
        patch("app.services.wiki_engine.get_llm_provider", return_value=provider),
    ):
        yield


async def test_rebuild_keeps_synthesis_and_reports_removed_pages(
    db_session: AsyncSession, tmp_path: Path
):
    class_id, wiki_path, _ = await _rebuild_fixture(db_session, tmp_path)
    provider = AsyncMock()
    provider.complete = AsyncMock(
        return_value=(
            '<wiki-page path="pages/concept/new-concept.md">\n'
            '---\ntitle: "New Concept"\ntype: concept\nsources: []\ntags: []\n---\n\n'
            "New text.\n</wiki-page>\n"
        )
    )

    with _rebuild_env(wiki_path, provider):
        result = await handle_rebuild(db_session, class_id)

    assert result.success is True
    assert (wiki_path / "pages" / "synthesis" / "overview.md").exists()
    assert result.pages_removed == ["pages/concept/old-concept.md"]
    assert result.pages_restored == []
    assert not (wiki_path / "pages" / "concept" / "old-concept.md").exists()


async def test_rebuild_restores_pages_when_reingest_fails(db_session: AsyncSession, tmp_path: Path):
    class_id, wiki_path, file_record = await _rebuild_fixture(db_session, tmp_path)
    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=RuntimeError("model unavailable"))

    with _rebuild_env(wiki_path, provider):
        result = await handle_rebuild(db_session, class_id)

    assert result.pages_restored == ["pages/concept/old-concept.md"]
    assert result.pages_removed == []
    assert result.failed_sources == ["notes.pdf: LLM error: model unavailable"]
    restored = wiki_path / "pages" / "concept" / "old-concept.md"
    assert "Old text." in restored.read_text(encoding="utf-8")
    row = (
        await db_session.execute(
            select(WikiPage).where(WikiPage.path == "pages/concept/old-concept.md")
        )
    ).scalar_one()
    assert row.source_file_ids == [str(file_record.id)]
    await db_session.refresh(file_record)
    assert file_record.status == FileStatus.READY


async def test_handle_rebuild_preview_lists_synthesis_as_preserved(
    db_session: AsyncSession, tmp_path: Path
):
    class_id, wiki_path, _ = await _rebuild_fixture(db_session, tmp_path)

    with patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path):
        preview = await handle_rebuild_preview(db_session, class_id)

    assert preview.pages_preserved_synthesis == ["pages/synthesis/overview.md"]
    assert preview.pages_to_delete == ["pages/concept/old-concept.md"]


# ---------------------------------------------------------------------------
# Streaming tests
# ---------------------------------------------------------------------------


async def test_handle_ask_stream_no_pages(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()
    (wiki_path / "index.md").write_text("# Index\n", encoding="utf-8")

    with patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path):
        chunks: list[str] = []
        async for chunk in handle_ask_stream(db_session, class_id, "What is X?"):
            chunks.append(chunk)

    full = "".join(chunks)
    assert "don't have any wiki pages" in full.lower() or "upload" in full.lower()


async def test_handle_ask_stream_yields_chunks(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()
    pages_dir = wiki_path / "pages"
    pages_dir.mkdir(parents=True)
    (wiki_path / "index.md").write_text("# Index\n- Topic\n", encoding="utf-8")
    (pages_dir / "topic.md").write_text(
        '---\ntitle: "Topic"\ntype: concept\n---\nContent about the topic.\n',
        encoding="utf-8",
    )

    page = WikiPage(
        class_id=class_id,
        path="pages/topic.md",
        title="Topic",
        category=WikiCategory.CONCEPT,
        content="Content about the topic.",
        source_file_ids=[],
    )
    db_session.add(page)
    await db_session.flush()

    from app.services.wiki_search import sync_fts_page

    await sync_fts_page(
        db_session,
        page_id=page.id,
        class_id=class_id,
        path="pages/topic.md",
        title="Topic",
        content="Content about the topic.",
        tags=["topic"],
    )
    await db_session.commit()

    async def mock_stream(*args, **kwargs):
        for word in ["Hello", " ", "world", "!"]:
            yield word

    mock_provider = MagicMock()
    mock_provider.stream = mock_stream

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.get_llm_provider", return_value=mock_provider),
    ):
        chunks: list[str] = []
        async for chunk in handle_ask_stream(db_session, class_id, "Tell me about topic"):
            chunks.append(chunk)

    assert len(chunks) == 4
    assert "".join(chunks) == "Hello world!"
