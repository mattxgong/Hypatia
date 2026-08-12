"""Tests for the ingestion queue (Task 3A.8)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db_models import Base, File, FileStatus, FileType
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
