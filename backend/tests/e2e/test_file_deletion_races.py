"""Deleting a file through the API while its conversion or ingestion is running.

Unlike the rest of the suite these tests replace the inert stub queue with a
real ``IngestionQueue`` bound to the E2E database, so the DELETE endpoint has a
live worker to cancel.
"""

from __future__ import annotations

import asyncio
import io
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.db_models import File, WikiPage
from app.services import ingestion_queue
from app.services.ingestion_queue import IngestionQueue, QueueItemStatus
from app.services.video_processor import ProcessingResult
from tests.e2e.conftest import MockLLMProvider

pytestmark = pytest.mark.asyncio

_TIMEOUT = 10


class BlockingLLMProvider(MockLLMProvider):
    """Blocks inside the first completion until the ingest worker is cancelled."""

    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def complete(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> str:
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return ""


@pytest.fixture
async def real_queue(
    e2e_client: AsyncClient,
    e2e_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[IngestionQueue]:
    queue = IngestionQueue(e2e_session_factory)
    monkeypatch.setattr(ingestion_queue, "_queue", queue)
    yield queue
    await queue.shutdown()


def _class_dir(class_id: str) -> Path:
    return settings.data_dir / "classes" / class_id


def _artifacts_for(class_id: str, file_id: str) -> list[Path]:
    converted = _class_dir(class_id) / "converted"
    return list(converted.glob(f"{file_id}.*")) if converted.exists() else []


async def _pages_citing(
    session_factory: async_sessionmaker[AsyncSession], file_id: str
) -> list[WikiPage]:
    async with session_factory() as session:
        pages = (await session.execute(select(WikiPage))).scalars().all()
    return [page for page in pages if file_id in (page.source_file_ids or [])]


async def test_delete_during_active_ingestion_cancels_worker(
    e2e_client: AsyncClient,
    e2e_class: dict,
    e2e_session_factory: async_sessionmaker[AsyncSession],
    real_queue: IngestionQueue,
    sample_source_file: Path,
) -> None:
    class_id = e2e_class["id"]
    llm = BlockingLLMProvider()

    with patch("app.services.wiki_engine.get_llm_provider", return_value=llm):
        upload = await e2e_client.post(
            f"/api/classes/{class_id}/files",
            files={"files": ("notes.md", io.BytesIO(sample_source_file.read_bytes()))},
        )
        assert upload.status_code == 202
        file_id = upload.json()[0]["id"]

        await asyncio.wait_for(llm.started.wait(), timeout=_TIMEOUT)
        status = await e2e_client.get(f"/api/classes/{class_id}/files/{file_id}")
        assert status.json()["status"] == "processing"

        delete = await e2e_client.delete(f"/api/classes/{class_id}/files/{file_id}")

    assert delete.status_code == 204
    assert llm.cancelled.is_set()
    item = real_queue.get_file_status(uuid.UUID(class_id), uuid.UUID(file_id))
    assert item is not None
    assert item.status == QueueItemStatus.FAILED
    assert item.error == "File deleted"

    assert (await e2e_client.get(f"/api/classes/{class_id}/files/{file_id}")).status_code == 404
    assert await _pages_citing(e2e_session_factory, file_id) == []
    assert _artifacts_for(class_id, file_id) == []
    assert list((_class_dir(class_id) / "raw").iterdir()) == []


async def test_delete_during_conversion_cancels_before_ingestion(
    e2e_client: AsyncClient,
    e2e_class: dict,
    e2e_session_factory: async_sessionmaker[AsyncSession],
    mock_llm: MockLLMProvider,
    real_queue: IngestionQueue,
    sample_source_file: Path,
) -> None:
    class_id = e2e_class["id"]
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def blocking_process_file(
        session: AsyncSession,
        file_id: uuid.UUID,
        raw_path: Path,
        output_path: Path,
        **_kwargs: object,
    ) -> ProcessingResult:
        # A partial artifact, as a converter leaves behind mid-write.
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("partial conversion", encoding="utf-8")
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return ProcessingResult(success=True, converted_path=output_path)

    with patch("app.routers.files.process_file", side_effect=blocking_process_file):
        # The ASGI transport runs background tasks before returning the
        # response, so the upload must be in flight while DELETE is sent.
        upload = asyncio.create_task(
            e2e_client.post(
                f"/api/classes/{class_id}/files",
                files={"files": ("notes.md", io.BytesIO(sample_source_file.read_bytes()))},
            )
        )
        await asyncio.wait_for(started.wait(), timeout=_TIMEOUT)

        listed = await e2e_client.get(f"/api/classes/{class_id}/files")
        file_id = listed.json()[0]["id"]
        delete = await e2e_client.delete(f"/api/classes/{class_id}/files/{file_id}")
        upload_response = await asyncio.wait_for(upload, timeout=_TIMEOUT)

    assert delete.status_code == 204
    assert upload_response.status_code == 202
    assert cancelled.is_set()
    assert real_queue.get_queue_status(uuid.UUID(class_id)) == []
    assert mock_llm.call_log == []

    async with e2e_session_factory() as session:
        assert await session.get(File, uuid.UUID(file_id)) is None
    assert await _pages_citing(e2e_session_factory, file_id) == []
    assert _artifacts_for(class_id, file_id) == []
    assert list((_class_dir(class_id) / "raw").iterdir()) == []
