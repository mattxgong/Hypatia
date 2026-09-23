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

import copy
import os
import uuid
from collections.abc import Coroutine, Iterator
from pathlib import Path
from typing import Any

import pytest

logs_dir = Path(__file__).resolve().parents[1] / ".pytest_cache" / "logs" / str(os.getpid())
os.environ["HYPATIA_LOGS_DIR"] = str(logs_dir)


class StubIngestionQueue:
    """Records what would have been ingested instead of touching the database."""

    def __init__(self) -> None:
        self.enqueued: list[tuple[uuid.UUID, uuid.UUID]] = []
        self.cancelled: list[uuid.UUID] = []
        self.cancelled_files: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def enqueue(self, class_id: uuid.UUID, file_id: uuid.UUID) -> None:
        self.enqueued.append((class_id, file_id))

    async def convert_and_enqueue(
        self,
        class_id: uuid.UUID,
        file_id: uuid.UUID,
        conversion: Coroutine[Any, Any, bool],
    ) -> None:
        if await conversion:
            self.enqueued.append((class_id, file_id))

    async def cancel_class(self, class_id: uuid.UUID) -> int:
        self.cancelled.append(class_id)
        return 0

    async def cancel_file(self, class_id: uuid.UUID, file_id: uuid.UUID) -> bool:
        self.cancelled_files.append((class_id, file_id))
        return False

    def is_ingesting(self, class_id: uuid.UUID, file_id: uuid.UUID) -> bool:
        return (class_id, file_id) in self.enqueued

    async def recover_pending(self) -> int:
        return 0

    async def shutdown(self) -> int:
        return 0


@pytest.fixture(autouse=True)
def stub_ingestion_queue() -> Iterator[StubIngestionQueue]:
    from app.services import ingestion_queue

    stub = StubIngestionQueue()
    original = ingestion_queue._queue
    ingestion_queue._queue = stub  # type: ignore[assignment]
    yield stub
    ingestion_queue._queue = original


class MemoryCredentialStore:
    """Stands in for the platform keyring so tests never read or write real secrets."""

    def __init__(self, _data_dir: Path) -> None:
        self._values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._values.get(key)

    def set(self, key: str, value: str) -> None:
        self._values[key] = value

    def delete(self, key: str) -> None:
        self._values.pop(key, None)


@pytest.fixture(autouse=True)
def isolate_global_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Restore every ``settings`` field after each test.

    The settings API and app lifespan mutate the process-wide singleton, so a
    provider switch in one test would otherwise leak into every later test.
    """
    from app.config import Settings, settings

    monkeypatch.setattr("app.main.CredentialStore", MemoryCredentialStore)
    snapshot = {name: copy.deepcopy(getattr(settings, name)) for name in Settings.model_fields}
    yield
    for name, value in snapshot.items():
        setattr(settings, name, value)
