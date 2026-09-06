"""Shared test fixtures.

The ingestion queue returned by ``get_ingestion_queue()`` is process-wide and
bound to the real ``async_session_factory``, which points at the developer's
``~/.hypatia/data/hypatia.db`` — tests only override the ``get_session``
dependency, not the module-level factory. Left alone, any test that runs the
app lifespan (``TestClient``) or an upload background task would enqueue real
files and start real LLM ingestion. Every test therefore gets an inert queue;
tests that exercise queue behaviour construct ``IngestionQueue`` directly.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from app.services import ingestion_queue


class StubIngestionQueue:
    """Records what would have been ingested instead of touching the database."""

    def __init__(self) -> None:
        self.enqueued: list[tuple[uuid.UUID, uuid.UUID]] = []
        self.cancelled: list[uuid.UUID] = []

    async def enqueue(self, class_id: uuid.UUID, file_id: uuid.UUID) -> None:
        self.enqueued.append((class_id, file_id))

    async def cancel_class(self, class_id: uuid.UUID) -> int:
        self.cancelled.append(class_id)
        return 0

    async def recover_pending(self) -> int:
        return 0


@pytest.fixture(autouse=True)
def stub_ingestion_queue() -> Iterator[StubIngestionQueue]:
    stub = StubIngestionQueue()
    original = ingestion_queue._queue
    ingestion_queue._queue = stub  # type: ignore[assignment]
    yield stub
    ingestion_queue._queue = original
