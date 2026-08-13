"""Comprehensive wiki engine tests (Task 3B.11).

Covers: error handling (LLM timeout, malformed output, parse failure),
git auto-commit, user edit preservation during ingest, streaming errors,
and edge cases not covered by earlier test files.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db_models import (
    Base,
    ChatMessage,
    Class,
    File,
    FileStatus,
    FileType,
    WikiCategory,
    WikiPage,
)
from app.services.wiki_engine import (
    IngestResult,
    handle_ask,
    handle_ask_stream,
    handle_lint,
    handle_remove,
    handle_summarize,
    ingest_source,
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


def _create_class_and_file(
    db_session: AsyncSession,
    class_id: uuid.UUID,
    tmp_path: Path,
    filename: str = "notes.pdf",
    content: str = "# Notes\n\nSome content about testing.",
) -> tuple[File, Path]:
    """Helper to create a Class, File record, and converted markdown file."""
    converted_path = tmp_path / "converted" / f"{Path(filename).stem}.md"
    converted_path.parent.mkdir(parents=True, exist_ok=True)
    converted_path.write_text(content, encoding="utf-8")

    raw_path = tmp_path / "raw" / filename
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(b"fake content")

    cls = Class(id=class_id, name=f"Test-{class_id.hex[:8]}")
    db_session.add(cls)

    file_record = File(
        class_id=class_id,
        original_filename=filename,
        file_type=FileType.PDF,
        file_size_bytes=len(b"fake content"),
        status=FileStatus.READY,
        raw_path=str(raw_path),
        converted_path=str(converted_path),
    )
    db_session.add(file_record)
    return file_record, converted_path


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


async def test_ingest_llm_timeout(db_session: AsyncSession, tmp_path: Path):
    """LLM timeout during ingest should return failure, not crash."""
    class_id = uuid.uuid4()
    file_record, _ = _create_class_and_file(db_session, class_id, tmp_path)
    await db_session.flush()

    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()
    (wiki_path / "index.md").write_text("# Index\n", encoding="utf-8")

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(side_effect=OSError("Connection timed out"))

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.init_wiki_repo", return_value=wiki_path),
        patch("app.services.wiki_engine.get_llm_provider", return_value=mock_provider),
        patch("app.services.wiki_engine.commit_wiki_change"),
    ):
        result = await ingest_source(db_session, class_id, file_record.id)

    assert isinstance(result, IngestResult)
    assert result.success is False
    assert "timed out" in (result.error or "").lower()


async def test_ingest_malformed_llm_output(db_session: AsyncSession, tmp_path: Path):
    """LLM returning garbage (no parseable pages) should be handled gracefully."""
    class_id = uuid.uuid4()
    file_record, _ = _create_class_and_file(db_session, class_id, tmp_path)
    await db_session.flush()

    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()
    (wiki_path / "index.md").write_text("# Index\n", encoding="utf-8")

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value="I'm sorry, I can't help with that request.")

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.init_wiki_repo", return_value=wiki_path),
        patch("app.services.wiki_engine.get_llm_provider", return_value=mock_provider),
        patch("app.services.wiki_engine.commit_wiki_change"),
    ):
        result = await ingest_source(db_session, class_id, file_record.id)

    assert result.success is False
    assert (
        "no parseable" in (result.error or "").lower() or "no valid" in (result.error or "").lower()
    )


async def test_summarize_llm_error(db_session: AsyncSession, tmp_path: Path):
    """LLM error during summarize should return SummarizeResult with error."""
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()
    pages_dir = wiki_path / "pages" / "concepts"
    pages_dir.mkdir(parents=True)
    (pages_dir / "test.md").write_text(
        '---\ntitle: "Test"\ntype: concept\n---\nTest content.\n', encoding="utf-8"
    )

    page = WikiPage(
        class_id=class_id,
        path="pages/concepts/test.md",
        title="Test",
        category=WikiCategory.CONCEPT,
        content="Test content.",
        source_file_ids=[],
    )
    db_session.add(page)
    await db_session.flush()

    from app.services.wiki_search import sync_fts_page

    await sync_fts_page(
        db_session,
        page_id=page.id,
        class_id=class_id,
        path="pages/concepts/test.md",
        title="Test",
        content="Test content.",
        tags=["test"],
    )
    await db_session.commit()

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(side_effect=RuntimeError("API rate limit exceeded"))

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.get_llm_provider", return_value=mock_provider),
    ):
        result = await handle_summarize(db_session, class_id, "test")

    assert result.success is False
    assert "LLM error" in (result.error or "")


async def test_ask_stream_llm_error_yields_error_message(db_session: AsyncSession, tmp_path: Path):
    """Streaming /ask should yield an error message if LLM fails mid-stream."""
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()
    pages_dir = wiki_path / "pages"
    pages_dir.mkdir()
    (wiki_path / "index.md").write_text("# Index\n", encoding="utf-8")
    (pages_dir / "topic.md").write_text(
        '---\ntitle: "Topic"\ntype: concept\n---\nContent.\n', encoding="utf-8"
    )

    page = WikiPage(
        class_id=class_id,
        path="pages/topic.md",
        title="Topic",
        category=WikiCategory.CONCEPT,
        content="Content.",
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
        content="Content.",
        tags=["topic"],
    )
    await db_session.commit()

    async def failing_stream(*args, **kwargs):
        yield "Partial "
        raise RuntimeError("connection reset")

    mock_provider = MagicMock()
    mock_provider.stream = failing_stream

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.get_llm_provider", return_value=mock_provider),
    ):
        chunks: list[str] = []
        async for chunk in handle_ask_stream(db_session, class_id, "topic question"):
            chunks.append(chunk)

    full = "".join(chunks)
    assert "Partial" in full
    assert "Error" in full


# ---------------------------------------------------------------------------
# Git auto-commit tests
# ---------------------------------------------------------------------------


async def test_update_wiki_page_commits_user_edit(db_session: AsyncSession, tmp_path: Path):
    """User edits should trigger a git commit with 'user-edit:' prefix."""
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()

    content = '---\ntitle: "Page"\ntype: concept\nsources: []\ntags: []\n---\nEdited.\n'

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.commit_wiki_change") as mock_commit,
    ):
        await update_wiki_page(
            db_session, class_id, "pages/concepts/test.md", content, is_user_edit=True
        )

    mock_commit.assert_called_once()
    commit_msg = mock_commit.call_args[0][1]
    assert commit_msg.startswith("user-edit:")


async def test_update_wiki_page_no_commit_for_non_user_edit(
    db_session: AsyncSession, tmp_path: Path
):
    """Non-user edits (LLM generated) should not trigger a git commit."""
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()

    content = '---\ntitle: "Page"\ntype: concept\nsources: []\ntags: []\n---\nGenerated.\n'

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.commit_wiki_change") as mock_commit,
    ):
        await update_wiki_page(
            db_session, class_id, "pages/concepts/test.md", content, is_user_edit=False
        )

    mock_commit.assert_not_called()


# ---------------------------------------------------------------------------
# User edit preservation during ingest
# ---------------------------------------------------------------------------


async def test_ingest_skips_user_edited_pages(db_session: AsyncSession, tmp_path: Path):
    """If LLM wants to update a user-edited page, it should not overwrite it."""
    class_id = uuid.uuid4()
    file_record, _ = _create_class_and_file(db_session, class_id, tmp_path)
    await db_session.flush()

    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()
    pages_dir = wiki_path / "pages" / "concepts"
    pages_dir.mkdir(parents=True)
    (wiki_path / "index.md").write_text("# Index\n", encoding="utf-8")

    user_page = pages_dir / "existing-concept.md"
    user_page.write_text(
        '---\ntitle: "Existing"\ntype: concept\nsources: []\n'
        "tags: []\nuser_edited: true\n---\n\n# My custom notes\n",
        encoding="utf-8",
    )

    existing_db_page = WikiPage(
        class_id=class_id,
        path="pages/concepts/existing-concept.md",
        title="Existing",
        category=WikiCategory.CONCEPT,
        content="My custom notes",
        source_file_ids=[],
    )
    db_session.add(existing_db_page)
    await db_session.flush()

    llm_output = (
        '<wiki-page path="pages/source-summaries/notes.md">\n'
        "---\n"
        'title: "Notes Summary"\n'
        "type: source-summary\n"
        f"sources: [{file_record.id}]\n"
        "tags: [notes]\n"
        "---\n\n# Notes Summary\n\nNew summary.\n"
        "</wiki-page>\n\n"
        '<wiki-page path="pages/concepts/existing-concept.md" action="update">\n'
        "---\n"
        'title: "Existing"\n'
        "type: concept\n"
        f"sources: [{file_record.id}]\n"
        "tags: [updated]\n"
        "---\n\n# Overwritten content\n"
        "</wiki-page>\n"
    )

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value=llm_output)

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.init_wiki_repo", return_value=wiki_path),
        patch("app.services.wiki_engine.get_llm_provider", return_value=mock_provider),
        patch("app.services.wiki_engine.commit_wiki_change"),
    ):
        result = await ingest_source(db_session, class_id, file_record.id)

    assert result.success is True
    preserved_content = user_page.read_text(encoding="utf-8")
    assert "My custom notes" in preserved_content
    assert "Overwritten content" not in preserved_content


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_handle_ask_empty_wiki(db_session: AsyncSession, tmp_path: Path):
    """Asking questions with no wiki pages should return a helpful message."""
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()
    (wiki_path / "index.md").write_text("# Index\n", encoding="utf-8")

    with patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path):
        result = await handle_ask(db_session, class_id, "What is machine learning?")

    assert "upload" in result.answer.lower() or "no" in result.answer.lower()


async def test_handle_remove_multi_source_page_preserved(db_session: AsyncSession, tmp_path: Path):
    """Removing a file that shares a wiki page with another source preserves the page."""
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()
    pages_dir = wiki_path / "pages" / "concepts"
    pages_dir.mkdir(parents=True)
    (wiki_path / "index.md").write_text("# Index\n", encoding="utf-8")
    (wiki_path / "log.md").write_text("# Log\n", encoding="utf-8")
    (pages_dir / "shared.md").write_text("# Shared concept\n", encoding="utf-8")

    cls = Class(id=class_id, name="MultiSrc")
    db_session.add(cls)
    await db_session.flush()

    raw_path = tmp_path / "raw" / "file-a.pdf"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(b"a")

    file_a = File(
        class_id=class_id,
        original_filename="file-a.pdf",
        file_type=FileType.PDF,
        file_size_bytes=1,
        status=FileStatus.READY,
        raw_path=str(raw_path),
    )
    db_session.add(file_a)
    await db_session.flush()
    file_a_id = str(file_a.id)

    file_b_id = str(uuid.uuid4())

    wiki_page = WikiPage(
        class_id=class_id,
        path="pages/concepts/shared.md",
        title="Shared",
        category=WikiCategory.CONCEPT,
        content="Shared concept.",
        source_file_ids=[file_a_id, file_b_id],
    )
    db_session.add(wiki_page)
    await db_session.flush()

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.commit_wiki_change"),
    ):
        result = await handle_remove(db_session, class_id, "file-a.pdf")

    assert result.success is True
    assert result.pages_deleted == []
    assert "pages/concepts/shared.md" in result.pages_updated

    q = await db_session.execute(
        select(WikiPage).where(WikiPage.path == "pages/concepts/shared.md")
    )
    page = q.scalar_one()
    assert file_a_id not in page.source_file_ids
    assert file_b_id in page.source_file_ids


async def test_lint_no_llm_for_small_wikis(db_session: AsyncSession, tmp_path: Path):
    """Wikis with fewer than 3 pages should skip LLM-based lint (only structural checks)."""
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    pages_dir = wiki_path / "pages"
    pages_dir.mkdir(parents=True)
    (wiki_path / "log.md").write_text("# Log\n", encoding="utf-8")

    (pages_dir / "one.md").write_text("---\ntitle: One\n---\nContent.\n", encoding="utf-8")
    (pages_dir / "two.md").write_text("---\ntitle: Two\n---\nContent [[one]].\n", encoding="utf-8")

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.get_llm_provider") as mock_get_provider,
    ):
        result = await handle_lint(db_session, class_id)

    mock_get_provider.assert_not_called()
    assert result.success is True


async def test_handle_ask_saves_to_chat_messages(db_session: AsyncSession, tmp_path: Path):
    """Both query and response should be saved to chat_messages table."""
    class_id = uuid.uuid4()
    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir()
    pages_dir = wiki_path / "pages"
    pages_dir.mkdir()
    (wiki_path / "index.md").write_text("# Index\n", encoding="utf-8")
    (pages_dir / "topic.md").write_text(
        '---\ntitle: "Topic"\ntype: concept\n---\nTopic content.\n', encoding="utf-8"
    )

    page = WikiPage(
        class_id=class_id,
        path="pages/topic.md",
        title="Topic",
        category=WikiCategory.CONCEPT,
        content="Topic content.",
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
        content="Topic content.",
        tags=["topic"],
    )
    await db_session.commit()

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value="The topic is about X.")

    with (
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
        patch("app.services.wiki_engine.get_llm_provider", return_value=mock_provider),
    ):
        await handle_ask(db_session, class_id, "What is the topic?")

    q = await db_session.execute(select(ChatMessage).where(ChatMessage.class_id == class_id))
    messages = q.scalars().all()
    assert len(messages) == 2
    roles = {m.role.value if hasattr(m.role, "value") else m.role for m in messages}
    assert "user" in roles
    assert "assistant" in roles
