"""Prompt budgets, truncated output, rate-limit retries, text decoding, timestamps."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.errors import ErrorCode, LLMProviderError
from app.models.db_models import Base, Class, File, FileStatus, FileType, WikiCategory, WikiPage
from app.services import wiki_engine
from app.services.file_converter import _decode_text
from app.services.ingestion_queue import IngestionQueue
from app.services.wiki_search import ensure_fts_index, sync_fts_page


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_fts_index(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _make_file(session: AsyncSession, class_id: uuid.UUID, tmp_path: Path, text: str) -> File:
    converted = tmp_path / f"{uuid.uuid4().hex}.md"
    converted.write_text(text, encoding="utf-8")
    session.add(Class(id=class_id, name=f"Class {class_id.hex[:8]}"))
    record = File(
        class_id=class_id,
        original_filename="notes.pdf",
        file_type=FileType.PDF,
        file_size_bytes=10,
        raw_path=str(tmp_path / "raw.pdf"),
        converted_path=str(converted),
        status=FileStatus.READY,
    )
    session.add(record)
    await session.commit()
    return record


def _page_xml(path: str, body: str) -> str:
    return (
        f'<wiki-page path="{path}">\n---\ntitle: "{Path(path).stem}"\ntype: concept\n'
        f"sources: []\ntags: []\n---\n\n{body}\n</wiki-page>\n"
    )


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


def test_prompt_budget_leaves_room_for_the_system_prompt_and_headroom():
    with (
        patch("app.services.wiki_engine.get_context_window", return_value=8000),
        patch("app.services.wiki_engine.settings.llm_max_tokens", 1000),
    ):
        system = "word " * 300
        bare = wiki_engine._prompt_budget()
        with_system = wiki_engine._prompt_budget(system)

    assert bare == 8000 - 1000 - 400  # output budget and 5% headroom
    assert with_system == bare - wiki_engine._count_tokens(system)


async def test_ask_skips_an_oversized_page_and_uses_smaller_ones(db_session: AsyncSession):
    class_id = uuid.uuid4()
    pages = {
        "pages/concepts/huge.md": "photosynthesis " * 3000,
        "pages/concepts/small.md": "Photosynthesis turns light into sugar.",
    }
    for path, content in pages.items():
        row = WikiPage(
            class_id=class_id,
            path=path,
            title=Path(path).stem,
            category=WikiCategory.CONCEPT,
            content=content,
        )
        db_session.add(row)
        await db_session.flush()
        await sync_fts_page(
            db_session,
            page_id=row.id,
            class_id=class_id,
            path=path,
            title=row.title,
            content=content,
        )
    await db_session.commit()

    with patch("app.services.wiki_engine.get_context_window", return_value=4096):
        _, consulted = await wiki_engine._ask_context(db_session, class_id, "photosynthesis")

    assert consulted == ["pages/concepts/small.md"]


# ---------------------------------------------------------------------------
# Truncated output and rate limits
# ---------------------------------------------------------------------------


async def test_truncated_ingest_output_retries_the_chunk_in_halves(
    db_session: AsyncSession, tmp_path: Path
):
    class_id = uuid.uuid4()
    text = "\n".join(f"Line {i} explains a separate idea in some detail." for i in range(80))
    record = await _make_file(db_session, class_id, tmp_path, text)
    provider = AsyncMock()
    calls = 0

    async def complete(*args: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        provider.last_truncated = calls == 1  # the first, whole-chunk answer is cut off
        return _page_xml(f"pages/concepts/part-{calls}.md", f"Part {calls}.")

    provider.complete = AsyncMock(side_effect=complete)

    with patch("app.services.wiki_engine.get_llm_provider", return_value=provider):
        result = await wiki_engine.ingest_source(db_session, class_id, record.id)

    assert calls == 3
    assert sorted(result.pages_created) == ["pages/concepts/part-2.md", "pages/concepts/part-3.md"]
    provider.close.assert_awaited_once()


async def test_ingest_progress_never_goes_backwards_when_a_chunk_is_split(
    db_session: AsyncSession, tmp_path: Path
):
    from app.services.task_manager import task_manager

    class_id = uuid.uuid4()
    record = await _make_file(db_session, class_id, tmp_path, "unused")
    long_chunk = "\n".join(f"Line {i} explains a separate idea in some detail." for i in range(120))
    chunks = ["# Part A\n\nShort.", long_chunk, "# Part C\n\nShort."]
    provider = AsyncMock()
    calls = 0

    async def complete(*args: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        provider.last_truncated = calls == 2  # the long middle chunk is cut off
        return _page_xml(f"pages/concepts/part-{calls}.md", f"Part {calls}.")

    provider.complete = AsyncMock(side_effect=complete)
    task_id = task_manager.start_task("Ingest", str(class_id))
    progress: list[int] = []
    real_update = task_manager.update_progress

    def record_progress(tid: str, value: int | None, message: str) -> None:
        if value is not None:
            progress.append(value)
        real_update(tid, value, message)

    with patch.object(task_manager, "update_progress", side_effect=record_progress):
        result = await wiki_engine._ingest_chunks(
            db_session,
            class_id,
            record,
            chunks,
            provider,
            task_id=task_id,
            related_budget=1000,
            index_budget=1000,
        )

    assert result.success
    assert calls == 5  # A, the cut-off middle, its two halves, C
    assert progress == sorted(progress), progress
    assert progress[0] == 0 and progress[-1] < 100


async def test_rate_limited_ingest_raises_and_leaves_the_file_ready(
    db_session: AsyncSession, tmp_path: Path
):
    class_id = uuid.uuid4()
    record = await _make_file(db_session, class_id, tmp_path, "# Notes\n\nText.")
    provider = AsyncMock()
    provider.complete = AsyncMock(
        side_effect=LLMProviderError(ErrorCode.LLM_RATE_LIMITED, "slow down")
    )

    with (
        patch("app.services.wiki_engine.get_llm_provider", return_value=provider),
        pytest.raises(LLMProviderError),
    ):
        await wiki_engine.ingest_source(db_session, class_id, record.id)

    await db_session.refresh(record)
    assert record.status == FileStatus.READY
    provider.close.assert_awaited_once()


def test_only_real_rate_limits_are_retried():
    assert IngestionQueue._is_rate_limit(LLMProviderError(ErrorCode.LLM_RATE_LIMITED, "x"))
    assert not IngestionQueue._is_rate_limit(LLMProviderError(ErrorCode.LLM_UNAVAILABLE, "rate"))
    assert IngestionQueue._is_rate_limit(RuntimeError("429 Too Many Requests"))
    assert not IngestionQueue._is_rate_limit(RuntimeError("could not generate a page"))


# ---------------------------------------------------------------------------
# Text decoding and timestamps
# ---------------------------------------------------------------------------


def test_text_files_saved_in_other_encodings_still_decode():
    assert _decode_text("café".encode()) == "café"
    assert _decode_text("café".encode("utf-8-sig")) == "café"
    assert _decode_text("naïve “quotes”".encode("cp1252")) == "naïve “quotes”"
    assert _decode_text(b"\x81\x8d broken").endswith("broken")


async def test_timestamps_come_back_as_utc(db_session: AsyncSession):
    plus_two = timezone(timedelta(hours=2))
    created = datetime(2026, 3, 1, 12, 0, tzinfo=plus_two)
    db_session.add(Class(id=uuid.uuid4(), name="Clock", created_at=created, updated_at=created))
    await db_session.commit()
    db_session.expunge_all()

    row = (await db_session.execute(select(Class).where(Class.name == "Clock"))).scalar_one()
    assert row.created_at == datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    assert row.created_at.utcoffset() == timedelta(0)
