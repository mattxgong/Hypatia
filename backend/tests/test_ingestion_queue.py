"""Tests for the ingestion queue (Task 3A.8)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.errors import LLMProviderError
from app.models.db_models import Base, File, FileStatus, FileType, WikiCategory, WikiPage
from app.services.ingestion_queue import IngestionQueue, QueueItemStatus
from app.services.wiki_engine import IngestResult
from app.services.wiki_search import ensure_fts_index


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_fts_index(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def queue(session_factory: async_sessionmaker[AsyncSession]) -> IngestionQueue:
    return IngestionQueue(session_factory)


async def test_enqueue_adds_item(queue: IngestionQueue):
    class_id = uuid.uuid4()
    file_id = uuid.uuid4()

    item = await queue.enqueue(class_id, file_id)
    assert item is not None
    assert item.status == QueueItemStatus.PENDING
    assert item.position == 1


async def test_enqueue_prevents_duplicates(queue: IngestionQueue):
    class_id = uuid.uuid4()
    file_id = uuid.uuid4()

    item1 = await queue.enqueue(class_id, file_id)
    item2 = await queue.enqueue(class_id, file_id)

    assert item1 is not None
    assert item2 is None


async def test_enqueue_multiple_files(queue: IngestionQueue):
    class_id = uuid.uuid4()
    file1 = uuid.uuid4()
    file2 = uuid.uuid4()

    item1 = await queue.enqueue(class_id, file1)
    item2 = await queue.enqueue(class_id, file2)

    assert item1 is not None
    assert item2 is not None
    assert item2.position == 2


async def test_get_queue_status(queue: IngestionQueue):
    class_id = uuid.uuid4()
    await queue.enqueue(class_id, uuid.uuid4())
    await queue.enqueue(class_id, uuid.uuid4())

    status = queue.get_queue_status(class_id)
    assert len(status) == 2


async def test_get_file_status(queue: IngestionQueue):
    class_id = uuid.uuid4()
    file_id = uuid.uuid4()

    await queue.enqueue(class_id, file_id)
    item = queue.get_file_status(class_id, file_id)
    assert item is not None
    assert item.file_id == file_id


async def test_get_file_status_not_found(queue: IngestionQueue):
    item = queue.get_file_status(uuid.uuid4(), uuid.uuid4())
    assert item is None


async def test_processes_sequentially(
    queue: IngestionQueue, session_factory: async_sessionmaker[AsyncSession]
):
    class_id = uuid.uuid4()
    file1 = uuid.uuid4()
    file2 = uuid.uuid4()

    async with session_factory() as session:
        for fid in (file1, file2):
            session.add(
                File(
                    id=fid,
                    class_id=class_id,
                    original_filename=f"{fid}.md",
                    file_type=FileType.MARKDOWN,
                    file_size_bytes=50,
                    raw_path=f"/tmp/{fid}.md",
                    converted_path=f"/tmp/{fid}_converted.md",
                    status=FileStatus.READY,
                )
            )
        await session.commit()

    mock_result = IngestResult(success=True, pages_created=["p.md"])

    with patch(
        "app.services.ingestion_queue.ingest_source",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        await queue.enqueue(class_id, file1)
        await queue.enqueue(class_id, file2)

        await asyncio.sleep(0.3)

    status = queue.get_queue_status(class_id)
    completed = [s for s in status if s.status == QueueItemStatus.COMPLETE]
    assert len(completed) == 2


async def test_failed_ingestion_marks_error(
    queue: IngestionQueue, session_factory: async_sessionmaker[AsyncSession]
):
    class_id = uuid.uuid4()
    file_id = uuid.uuid4()

    async with session_factory() as session:
        session.add(
            File(
                id=file_id,
                class_id=class_id,
                original_filename="bad.md",
                file_type=FileType.MARKDOWN,
                file_size_bytes=50,
                raw_path="/tmp/bad.md",
                converted_path="/tmp/bad_converted.md",
                status=FileStatus.READY,
            )
        )
        await session.commit()

    mock_result = IngestResult(success=False, error="LLM error")

    with patch(
        "app.services.ingestion_queue.ingest_source",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        await queue.enqueue(class_id, file_id)
        await asyncio.sleep(0.2)

    item = queue.get_file_status(class_id, file_id)
    assert item is not None
    assert item.status == QueueItemStatus.FAILED
    assert item.error == "LLM error"


async def test_recover_pending_enqueues_only_uningested_files(
    queue: IngestionQueue, session_factory: async_sessionmaker[AsyncSession]
):
    """Converted files with no wiki page are recovered; already-ingested ones are not."""
    class_id = uuid.uuid4()
    ingested = uuid.uuid4()
    orphaned = uuid.uuid4()
    stuck = uuid.uuid4()
    unconverted = uuid.uuid4()

    async with session_factory() as session:
        for fid, converted, status in (
            (ingested, f"/tmp/{ingested}.md", FileStatus.READY),
            (orphaned, f"/tmp/{orphaned}.md", FileStatus.READY),
            (stuck, f"/tmp/{stuck}.md", FileStatus.PROCESSING),
            (unconverted, None, FileStatus.READY),
        ):
            session.add(
                File(
                    id=fid,
                    class_id=class_id,
                    original_filename=f"{fid}.md",
                    file_type=FileType.MARKDOWN,
                    file_size_bytes=50,
                    raw_path=f"/tmp/{fid}_raw.md",
                    converted_path=converted,
                    status=status,
                )
            )
        session.add(
            WikiPage(
                class_id=class_id,
                path="sources/ingested.md",
                title="Ingested",
                category=WikiCategory.SOURCE_SUMMARY,
                content="# Ingested",
                source_file_ids=[str(ingested)],
            )
        )
        await session.commit()

    with patch(
        "app.services.ingestion_queue.ingest_source",
        new_callable=AsyncMock,
        return_value=IngestResult(success=True, pages_created=["p.md"]),
    ):
        count = await queue.recover_pending()
        await asyncio.sleep(0.2)

    assert count == 2
    queued = {item.file_id for item in queue.get_queue_status(class_id)}
    assert queued == {orphaned, stuck}

    async with session_factory() as session:
        recovered = await session.get(File, stuck)
        assert recovered is not None
        assert recovered.status == FileStatus.READY


async def test_raised_error_is_contained_and_queue_continues(
    queue: IngestionQueue, session_factory: async_sessionmaker[AsyncSession]
):
    """An exception from ingest_source must not kill the per-Class worker.

    Regression test: LLMProviderError is a HypatiaError, which the old
    ``except (OSError, ValueError, RuntimeError)`` did not catch, so it escaped
    ``_process_class`` and abandoned every file still queued for the Class.
    """
    class_id = uuid.uuid4()
    file1 = uuid.uuid4()
    file2 = uuid.uuid4()

    async with session_factory() as session:
        for fid in (file1, file2):
            session.add(
                File(
                    id=fid,
                    class_id=class_id,
                    original_filename=f"{fid}.md",
                    file_type=FileType.MARKDOWN,
                    file_size_bytes=50,
                    raw_path=f"/tmp/{fid}.md",
                    converted_path=f"/tmp/{fid}_converted.md",
                    status=FileStatus.READY,
                )
            )
        await session.commit()

    boom = LLMProviderError(detail="request (7109 tokens) exceeds the available context size")

    with patch(
        "app.services.ingestion_queue.ingest_source",
        new_callable=AsyncMock,
        side_effect=boom,
    ) as mock_ingest:
        await queue.enqueue(class_id, file1)
        await queue.enqueue(class_id, file2)
        await asyncio.sleep(0.3)

    # The second file was still attempted, so the worker survived the first failure.
    assert mock_ingest.await_count == 2

    status = queue.get_queue_status(class_id)
    assert len(status) == 2
    assert all(item.status == QueueItemStatus.FAILED for item in status)

    # Both files are marked ERROR, so recover_pending won't re-queue them forever.
    async with session_factory() as session:
        for fid in (file1, file2):
            f = await session.get(File, fid)
            assert f is not None
            assert f.status == FileStatus.ERROR
            assert f.error_message is not None


async def test_one_file_at_a_time_per_class(
    queue: IngestionQueue, session_factory: async_sessionmaker[AsyncSession]
):
    """Two quick enqueues must not spawn two workers on the same wiki."""
    class_id = uuid.uuid4()
    file1 = uuid.uuid4()
    file2 = uuid.uuid4()

    async with session_factory() as session:
        for fid in (file1, file2):
            session.add(
                File(
                    id=fid,
                    class_id=class_id,
                    original_filename=f"{fid}.md",
                    file_type=FileType.MARKDOWN,
                    file_size_bytes=50,
                    raw_path=f"/tmp/{fid}.md",
                    converted_path=f"/tmp/{fid}_converted.md",
                    status=FileStatus.READY,
                )
            )
        await session.commit()

    in_flight = 0
    peak = 0

    async def slow_ingest(*args: object, **kwargs: object) -> IngestResult:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return IngestResult(success=True, pages_created=["p.md"])

    with patch("app.services.ingestion_queue.ingest_source", side_effect=slow_ingest):
        await queue.enqueue(class_id, file1)
        await queue.enqueue(class_id, file2)
        await asyncio.sleep(0.4)

    assert peak == 1
    assert all(i.status == QueueItemStatus.COMPLETE for i in queue.get_queue_status(class_id))


async def test_cancel_class_stops_worker(
    queue: IngestionQueue, session_factory: async_sessionmaker[AsyncSession]
):
    """Deleting a Class must abandon its queue instead of ingesting into a dead wiki."""
    class_id = uuid.uuid4()
    file1 = uuid.uuid4()
    file2 = uuid.uuid4()

    async with session_factory() as session:
        for fid in (file1, file2):
            session.add(
                File(
                    id=fid,
                    class_id=class_id,
                    original_filename=f"{fid}.md",
                    file_type=FileType.MARKDOWN,
                    file_size_bytes=50,
                    raw_path=f"/tmp/{fid}.md",
                    converted_path=f"/tmp/{fid}_converted.md",
                    status=FileStatus.READY,
                )
            )
        await session.commit()

    worker_released = asyncio.Event()

    async def slow_ingest(*args: object, **kwargs: object) -> IngestResult:
        try:
            await asyncio.sleep(0.5)
            return IngestResult(success=True, pages_created=["p.md"])
        finally:
            worker_released.set()

    with patch(
        "app.services.ingestion_queue.ingest_source", side_effect=slow_ingest
    ) as mock_ingest:
        await queue.enqueue(class_id, file1)
        await queue.enqueue(class_id, file2)
        await asyncio.sleep(0.05)

        abandoned = await queue.cancel_class(class_id)
        assert worker_released.is_set()
        await asyncio.sleep(0.6)

    assert abandoned == 2
    # The second file was never started, and the first was cut off mid-ingest.
    assert mock_ingest.call_count == 1
    assert queue.get_queue_status(class_id) == []


async def test_cancel_class_unknown_is_noop(queue: IngestionQueue):
    assert await queue.cancel_class(uuid.uuid4()) == 0
