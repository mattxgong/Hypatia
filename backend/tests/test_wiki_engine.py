"""Tests for the wiki engine (Tasks 3A.5, 3A.7)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db_models import Base, ChatMessage, File, FileStatus, FileType, WikiPage
from app.services.wiki_engine import handle_ask, ingest_source
from app.services.wiki_search import ensure_fts_index, sync_fts_page

MOCK_LLM_OUTPUT = """\
<wiki-page path="pages/source-summaries/test-doc.md">
---
title: "Test Document Summary"
type: source-summary
sources: [{file_id}]
tags: [testing, example]
---
# Test Document Summary

This is a summary of the test document. The document covers testing concepts
[source](hypatia://cite?file=test-doc.md&page=1).
</wiki-page>

<wiki-page path="pages/concepts/unit-testing.md">
---
title: "Unit Testing"
type: concept
sources: [{file_id}]
tags: [testing, software-engineering]
---
## Unit Testing

Unit testing is the practice of testing individual components in isolation.
See also [[integration-testing]].
[source](hypatia://cite?file=test-doc.md&section=unit-testing)
</wiki-page>
"""


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


def _create_test_file(tmp_path: Path, class_id: uuid.UUID, file_id: uuid.UUID) -> File:
    """Create a File record and write a converted markdown file on disk."""
    converted_dir = tmp_path / "converted"
    converted_dir.mkdir(parents=True, exist_ok=True)
    converted_file = converted_dir / "test-doc.md"
    converted_file.write_text(
        "# Test Document\n\n## Unit Testing\n\nUnit testing is important.\n",
        encoding="utf-8",
    )

    return File(
        id=file_id,
        class_id=class_id,
        original_filename="test-doc.md",
        file_type=FileType.MARKDOWN,
        file_size_bytes=100,
        raw_path=str(tmp_path / "raw" / "test-doc.md"),
        converted_path=str(converted_file),
        status=FileStatus.READY,
    )


async def test_ingest_source_success(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    file_id = uuid.uuid4()

    file_record = _create_test_file(tmp_path, class_id, file_id)
    db_session.add(file_record)
    await db_session.flush()

    mock_output = MOCK_LLM_OUTPUT.format(file_id=str(file_id))

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value=mock_output)

    with (
        patch("app.services.wiki_engine.get_llm_provider", return_value=mock_provider),
        patch("app.services.wiki_engine.init_wiki_repo", return_value=tmp_path / "wiki"),
        patch("app.services.wiki_engine.wiki_dir", return_value=tmp_path / "wiki"),
        patch("app.services.wiki_engine.commit_wiki_change", return_value="abc123"),
    ):
        (tmp_path / "wiki").mkdir(parents=True, exist_ok=True)
        result = await ingest_source(db_session, class_id, file_id)

    assert result.success is True
    assert len(result.pages_created) == 2
    assert "pages/source-summaries/test-doc.md" in result.pages_created
    assert "pages/concepts/unit-testing.md" in result.pages_created


async def test_ingest_source_file_not_found(db_session: AsyncSession):
    result = await ingest_source(db_session, uuid.uuid4(), uuid.uuid4())
    assert result.success is False
    assert result.error == "File not found"


async def test_ingest_source_file_not_ready(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    file_id = uuid.uuid4()

    file_record = File(
        id=file_id,
        class_id=class_id,
        original_filename="x.pdf",
        file_type=FileType.PDF,
        file_size_bytes=100,
        raw_path="/tmp/x.pdf",
        status=FileStatus.PROCESSING,
    )
    db_session.add(file_record)
    await db_session.flush()

    result = await ingest_source(db_session, class_id, file_id)
    assert result.success is False
    assert "status is processing" in result.error


async def test_ingest_creates_wiki_pages_in_db(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    file_id = uuid.uuid4()

    file_record = _create_test_file(tmp_path, class_id, file_id)
    db_session.add(file_record)
    await db_session.flush()

    mock_output = MOCK_LLM_OUTPUT.format(file_id=str(file_id))
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value=mock_output)

    with (
        patch("app.services.wiki_engine.get_llm_provider", return_value=mock_provider),
        patch("app.services.wiki_engine.init_wiki_repo", return_value=tmp_path / "wiki"),
        patch("app.services.wiki_engine.wiki_dir", return_value=tmp_path / "wiki"),
        patch("app.services.wiki_engine.commit_wiki_change", return_value="abc123"),
    ):
        (tmp_path / "wiki").mkdir(parents=True, exist_ok=True)
        await ingest_source(db_session, class_id, file_id)

    from sqlalchemy import select

    result = await db_session.execute(select(WikiPage).where(WikiPage.class_id == class_id))
    pages = result.scalars().all()
    assert len(pages) == 2
    titles = {p.title for p in pages}
    assert "Test Document Summary" in titles
    assert "Unit Testing" in titles


async def test_handle_ask_no_pages(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()

    with patch("app.services.wiki_engine.wiki_dir", return_value=tmp_path / "wiki"):
        (tmp_path / "wiki").mkdir(parents=True, exist_ok=True)
        result = await handle_ask(db_session, class_id, "What is testing?")

    assert "don't have any wiki pages" in result.answer
    assert result.pages_consulted == []


async def test_handle_ask_with_pages(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    page_id = uuid.uuid4()

    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir(parents=True, exist_ok=True)
    pages_dir = wiki_path / "pages" / "concepts"
    pages_dir.mkdir(parents=True, exist_ok=True)

    page_content = (
        '---\ntitle: "Unit Testing"\ntype: concept\n---\n\n'
        "Unit testing verifies individual components work correctly.\n"
    )
    (pages_dir / "unit-testing.md").write_text(page_content, encoding="utf-8")
    (wiki_path / "index.md").write_text("# Index\n- Unit Testing\n", encoding="utf-8")

    await sync_fts_page(
        db_session,
        page_id=page_id,
        class_id=class_id,
        path="pages/concepts/unit-testing.md",
        title="Unit Testing",
        content="Unit testing verifies individual components work correctly.",
        tags=["testing"],
    )
    await db_session.commit()

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value="Unit testing is about verifying components.")

    with (
        patch("app.services.wiki_engine.get_llm_provider", return_value=mock_provider),
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
    ):
        result = await handle_ask(db_session, class_id, "What is unit testing?")

    assert result.answer == "Unit testing is about verifying components."
    assert "pages/concepts/unit-testing.md" in result.pages_consulted
    mock_provider.complete.assert_called_once()


async def test_handle_ask_saves_chat_messages(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    page_id = uuid.uuid4()

    wiki_path = tmp_path / "wiki"
    wiki_path.mkdir(parents=True, exist_ok=True)
    pages_dir = wiki_path / "pages" / "concepts"
    pages_dir.mkdir(parents=True, exist_ok=True)
    (pages_dir / "x.md").write_text('---\ntitle: "X"\ntype: concept\n---\nContent.\n')
    (wiki_path / "index.md").write_text("# Index\n")

    await sync_fts_page(
        db_session,
        page_id=page_id,
        class_id=class_id,
        path="pages/concepts/x.md",
        title="X",
        content="Content about X.",
    )
    await db_session.commit()

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value="Answer about X.")

    with (
        patch("app.services.wiki_engine.get_llm_provider", return_value=mock_provider),
        patch("app.services.wiki_engine.wiki_dir", return_value=wiki_path),
    ):
        await handle_ask(db_session, class_id, "What is X?")

    from sqlalchemy import select

    result = await db_session.execute(select(ChatMessage).where(ChatMessage.class_id == class_id))
    messages = result.scalars().all()
    assert len(messages) == 2
    assert messages[0].role.value == "user"
    assert messages[1].role.value == "assistant"
