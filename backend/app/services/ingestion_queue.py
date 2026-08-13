"""Per-Class ingestion queue for sequential file processing (Task 3A.8).

Files are processed one at a time per Class to maintain wiki consistency and
respect LLM rate limits. Multiple Classes can process in parallel since they
are independent.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.db_models import File, FileStatus
from app.services.wiki_engine import IngestResult, ingest_source
from app.utils.logging import get_logger

logger = get_logger()


class QueueItemStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class QueueItem:
    class_id: uuid.UUID
    file_id: uuid.UUID
    status: QueueItemStatus = QueueItemStatus.PENDING
    error: str | None = None
    position: int = 0


@dataclass
class ClassQueue:
    """Per-class queue state."""

    items: list[QueueItem] = field(default_factory=list)
    processing: bool = False
    task: asyncio.Task | None = field(default=None, repr=False)


class IngestionQueue:
    """Manages per-Class sequential ingestion of source files."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._queues: dict[uuid.UUID, ClassQueue] = {}
        self._lock = asyncio.Lock()

    async def enqueue(self, class_id: uuid.UUID, file_id: uuid.UUID) -> QueueItem | None:
        """Add a file to the processing queue. Returns the queue item, or None
        if the file is already queued/processing."""
        async with self._lock:
            cq = self._queues.setdefault(class_id, ClassQueue())

            for item in cq.items:
                if item.file_id == file_id and item.status in (
                    QueueItemStatus.PENDING,
                    QueueItemStatus.PROCESSING,
                ):
                    logger.debug("ingest_already_queued", file_id=str(file_id))
                    return None

            position = sum(1 for it in cq.items if it.status == QueueItemStatus.PENDING) + 1
            item = QueueItem(class_id=class_id, file_id=file_id, position=position)
            cq.items.append(item)

            if not cq.processing:
                cq.task = asyncio.create_task(self._process_class(class_id))

            logger.info(
                "ingest_enqueued",
                class_id=str(class_id),
                file_id=str(file_id),
                position=position,
            )
            return item

    def get_queue_status(self, class_id: uuid.UUID) -> list[QueueItem]:
        """Return all queue items for a Class."""
        cq = self._queues.get(class_id)
        if not cq:
            return []
        return list(cq.items)

    def get_file_status(self, class_id: uuid.UUID, file_id: uuid.UUID) -> QueueItem | None:
        """Get the queue status of a specific file."""
        cq = self._queues.get(class_id)
        if not cq:
            return None
        for item in cq.items:
            if item.file_id == file_id:
                return item
        return None

    async def _process_class(self, class_id: uuid.UUID) -> None:
        """Process all pending items for a Class sequentially."""
        cq = self._queues[class_id]
        cq.processing = True

        try:
            while True:
                item = self._next_pending(cq)
                if item is None:
                    break

                item.status = QueueItemStatus.PROCESSING
                self._update_positions(cq)

                result = await self._process_single(item)

                if result.success:
                    item.status = QueueItemStatus.COMPLETE
                else:
                    item.status = QueueItemStatus.FAILED
                    item.error = result.error
        finally:
            cq.processing = False

    async def _process_single(self, item: QueueItem) -> IngestResult:
        """Process a single file with rate-limit retry."""
        max_retries = 3
        base_delay = 5.0

        for attempt in range(max_retries):
            try:
                async with self._session_factory() as session:
                    result = await ingest_source(session, item.class_id, item.file_id)

                    if not result.success:
                        await session.execute(
                            update(File)
                            .where(File.id == item.file_id)
                            .values(status=FileStatus.ERROR, error_message=result.error)
                        )
                        await session.commit()

                    return result

            except (OSError, ValueError, RuntimeError) as e:
                error_str = str(e).lower()
                is_rate_limit = "rate" in error_str or "429" in error_str

                if is_rate_limit and attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "ingest_rate_limited",
                        file_id=str(item.file_id),
                        attempt=attempt + 1,
                        retry_delay=delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error(
                    "ingest_failed",
                    file_id=str(item.file_id),
                    error=str(e),
                )
                return IngestResult(success=False, error=str(e))

        return IngestResult(success=False, error="Max retries exceeded")

    @staticmethod
    def _next_pending(cq: ClassQueue) -> QueueItem | None:
        for item in cq.items:
            if item.status == QueueItemStatus.PENDING:
                return item
        return None

    @staticmethod
    def _update_positions(cq: ClassQueue) -> None:
        pos = 1
        for item in cq.items:
            if item.status == QueueItemStatus.PENDING:
                item.position = pos
                pos += 1
            else:
                item.position = 0

    async def recover_pending(self) -> int:
        """Re-queue files stuck in PROCESSING state after a restart.

        Files in PROCESSING were mid-ingestion when the app stopped. Reset them
        to READY so ingest_source will accept them, then enqueue for retry.
        Returns the number of files re-queued.
        """
        count = 0
        async with self._session_factory() as session:
            result = await session.execute(select(File).where(File.status == FileStatus.PROCESSING))
            stuck_files = result.scalars().all()
            for f in stuck_files:
                f.status = FileStatus.READY
            await session.commit()

            for f in stuck_files:
                queued = await self.enqueue(f.class_id, f.id)
                if queued:
                    count += 1

        if count:
            logger.info("ingest_queue_recovered", count=count)
        return count
