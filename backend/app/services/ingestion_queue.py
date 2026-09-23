"""Per-Class ingestion queue for sequential file processing (Task 3A.8).

Files are processed one at a time per Class to maintain wiki consistency and
respect LLM rate limits. Multiple Classes can process in parallel since they
are independent.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine
from contextlib import suppress
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.errors import ErrorCode, HypatiaError
from app.models.db_models import File, FileStatus, WikiPage
from app.services.task_manager import task_manager
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


@dataclass
class _Conversion:
    class_id: uuid.UUID
    task: asyncio.Task[bool] = field(repr=False)
    cancelled: bool = False


class IngestionQueue:
    """Manages per-Class sequential ingestion of source files."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._queues: dict[uuid.UUID, ClassQueue] = {}
        self._conversions: dict[uuid.UUID, _Conversion] = {}
        self._lock = asyncio.Lock()

    async def enqueue(self, class_id: uuid.UUID, file_id: uuid.UUID) -> QueueItem | None:
        """Add a file to the processing queue. Returns the queue item, or None
        if the file is already queued/processing."""
        async with self._lock:
            return self._enqueue_locked(class_id, file_id)

    async def convert_and_enqueue(
        self,
        class_id: uuid.UUID,
        file_id: uuid.UUID,
        conversion: Coroutine[Any, Any, bool],
    ) -> QueueItem | None:
        """Run a file's conversion, then queue it if the conversion succeeded.

        The conversion is cancellable through :meth:`cancel_file`. Completion and
        cancellation are both decided under the lock, so a deleted file is
        either cancelled here or already queued where ``cancel_file`` finds it.
        """
        entry = _Conversion(class_id=class_id, task=asyncio.create_task(conversion))
        async with self._lock:
            self._conversions[file_id] = entry

        try:
            await asyncio.wait({entry.task})
        except asyncio.CancelledError:
            entry.task.cancel()
            raise

        async with self._lock:
            if self._conversions.get(file_id) is entry:
                del self._conversions[file_id]
            if entry.cancelled or entry.task.cancelled():
                return None
            exc = entry.task.exception()
            if exc is not None:
                logger.error("file_conversion_crashed", file_id=str(file_id), error=str(exc))
                return None
            if not entry.task.result():
                return None
            return self._enqueue_locked(class_id, file_id)

    def _enqueue_locked(self, class_id: uuid.UUID, file_id: uuid.UUID) -> QueueItem | None:
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
            # Claim the class here, under the lock, rather than letting the
            # worker set the flag once it starts: two files enqueued back to
            # back would both observe `processing is False` and spawn a
            # worker each, ingesting into the same wiki concurrently.
            cq.processing = True
            cq.task = asyncio.create_task(self._process_class(class_id))

        logger.info(
            "ingest_enqueued",
            class_id=str(class_id),
            file_id=str(file_id),
            position=position,
        )
        return item

    def _pop_conversions_locked(
        self, class_id: uuid.UUID | None = None, file_id: uuid.UUID | None = None
    ) -> list[asyncio.Task[bool]]:
        matches = [
            fid
            for fid, entry in self._conversions.items()
            if (class_id is None or entry.class_id == class_id)
            and (file_id is None or fid == file_id)
        ]
        tasks: list[asyncio.Task[bool]] = []
        for fid in matches:
            entry = self._conversions.pop(fid)
            entry.cancelled = True
            entry.task.cancel()
            tasks.append(entry.task)
        return tasks

    @staticmethod
    async def _wait_cancelled(tasks: list[asyncio.Task[bool]]) -> None:
        if tasks:
            await asyncio.wait(tasks)

    async def cancel_class(self, class_id: uuid.UUID) -> int:
        """Drop a Class's queue and stop its worker. Returns items abandoned.

        Called when a Class is deleted: an ingest already in flight would keep
        prompting the LLM for a wiki whose files and directories are gone, and
        eventually crash writing to the deleted wiki repo.
        """
        async with self._lock:
            cq = self._queues.pop(class_id, None)
            conversions = self._pop_conversions_locked(class_id=class_id)

        await self._wait_cancelled(conversions)
        abandoned = len(conversions)
        if cq is None:
            return abandoned

        for item in cq.items:
            if item.status in (QueueItemStatus.PENDING, QueueItemStatus.PROCESSING):
                item.status = QueueItemStatus.FAILED
                item.error = "Class deleted"
                abandoned += 1

        if cq.task is not None and not cq.task.done():
            cq.task.cancel()
            with suppress(asyncio.CancelledError):
                await cq.task

        if abandoned:
            logger.info("ingest_queue_cancelled", class_id=str(class_id), abandoned=abandoned)
        return abandoned

    async def cancel_file(self, class_id: uuid.UUID, file_id: uuid.UUID) -> bool:
        """Abandon one file's conversion or ingestion, preserving the rest of its Class queue."""
        task: asyncio.Task | None = None
        async with self._lock:
            conversions = self._pop_conversions_locked(class_id=class_id, file_id=file_id)
            cq = self._queues.get(class_id)
            item = (
                None
                if cq is None
                else next(
                    (
                        queued
                        for queued in cq.items
                        if queued.file_id == file_id
                        and queued.status in (QueueItemStatus.PENDING, QueueItemStatus.PROCESSING)
                    ),
                    None,
                )
            )
            if cq is not None and item is not None:
                was_processing = item.status == QueueItemStatus.PROCESSING
                item.status = QueueItemStatus.FAILED
                item.error = "File deleted"
                self._update_positions(cq)

                if was_processing and cq.task is not None and not cq.task.done():
                    task = cq.task

        await self._wait_cancelled(conversions)
        if not conversions and item is None:
            return False

        if task is not None and cq is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

            async with self._lock:
                if self._queues.get(class_id) is cq and cq.task is task:
                    cq.processing = False
                    cq.task = None
                    if self._next_pending(cq) is not None:
                        cq.processing = True
                        cq.task = asyncio.create_task(self._process_class(class_id))

        logger.info(
            "ingest_file_cancelled",
            class_id=str(class_id),
            file_id=str(file_id),
        )
        return True

    async def shutdown(self) -> int:
        """Cancel all workers before application or database shutdown."""
        async with self._lock:
            queues = list(self._queues.values())
            self._queues.clear()
            conversions = self._pop_conversions_locked()

        await self._wait_cancelled(conversions)
        tasks: list[asyncio.Task] = []
        abandoned = len(conversions)
        for cq in queues:
            for item in cq.items:
                if item.status in (QueueItemStatus.PENDING, QueueItemStatus.PROCESSING):
                    item.status = QueueItemStatus.FAILED
                    item.error = "Application shutdown"
                    abandoned += 1
            if cq.task is not None and not cq.task.done():
                cq.task.cancel()
                tasks.append(cq.task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if abandoned:
            logger.info("ingest_queue_shutdown", abandoned=abandoned)
        return abandoned

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

    def is_ingesting(self, class_id: uuid.UUID, file_id: uuid.UUID) -> bool:
        """Whether a file is waiting in, or being processed by, its Class queue."""
        cq = self._queues.get(class_id)
        return cq is not None and any(
            item.file_id == file_id
            and item.status in (QueueItemStatus.PENDING, QueueItemStatus.PROCESSING)
            for item in cq.items
        )

    async def _process_class(self, class_id: uuid.UUID) -> None:
        """Process all pending items for a Class sequentially."""
        while True:
            # Claiming the next item and releasing the class are both done under
            # the lock, so an enqueue that lands while this worker is winding
            # down either hands us another item or spawns a fresh worker —
            # never neither.
            async with self._lock:
                cq = self._queues.get(class_id)
                if cq is None:
                    return  # Class deleted.

                item = self._next_pending(cq)
                if item is None:
                    cq.processing = False
                    return

                item.status = QueueItemStatus.PROCESSING
                self._update_positions(cq)

            result = await self._process_single(item)

            async with self._lock:
                if self._queues.get(class_id) is not cq:
                    return  # Class deleted while this file was being ingested.

                if result.success:
                    item.status = QueueItemStatus.COMPLETE
                else:
                    item.status = QueueItemStatus.FAILED
                    item.error = result.error

    async def _process_single(self, item: QueueItem) -> IngestResult:
        """Process a single file with rate-limit retry.

        Never raises: this runs inside the per-Class worker task, so an escaping
        exception would kill the worker and silently abandon every file still
        queued for that Class.
        """
        max_retries = 3
        base_delay = 5.0
        task_id = task_manager.start_task("ingest", str(item.class_id))
        try:
            result = await self._ingest_with_retry(item, task_id, max_retries, base_delay)
        except asyncio.CancelledError:
            task_manager.cancel_task(task_id)
            raise
        if result.success:
            task_manager.complete_task(task_id)
        else:
            task_manager.fail_task(task_id, result.error or "Ingestion failed")
        return result

    async def _ingest_with_retry(
        self, item: QueueItem, task_id: str, max_retries: int, base_delay: float
    ) -> IngestResult:
        for attempt in range(max_retries):
            try:
                async with self._session_factory() as session:
                    result = await ingest_source(
                        session, item.class_id, item.file_id, task_id=task_id
                    )

                    if not result.success:
                        await self._mark_error(session, item.file_id, result.error)

                    return result

            except Exception as e:
                if self._is_rate_limit(e) and attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "ingest_rate_limited",
                        file_id=str(item.file_id),
                        attempt=attempt + 1,
                        retry_delay=delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.exception(
                    "ingest_failed",
                    file_id=str(item.file_id),
                    error=str(e),
                )
                await self._mark_error_safe(item.file_id, str(e))
                return IngestResult(success=False, error=str(e))

        return IngestResult(success=False, error="Max retries exceeded")

    @staticmethod
    def _is_rate_limit(exc: Exception) -> bool:
        if isinstance(exc, HypatiaError) and exc.code == ErrorCode.LLM_RATE_LIMITED:
            return True
        error_str = str(exc).lower()
        return "rate" in error_str or "429" in error_str

    @staticmethod
    async def _mark_error(session: AsyncSession, file_id: uuid.UUID, message: str | None) -> None:
        await session.execute(
            update(File)
            .where(File.id == file_id)
            .values(status=FileStatus.ERROR, error_message=message)
        )
        await session.commit()

    async def _mark_error_safe(self, file_id: uuid.UUID, message: str) -> None:
        """Record the failure on the file, on a session of its own.

        The session that raised may be in an unusable state, and a file left at
        READY would be re-queued by ``recover_pending`` on every restart.
        """
        try:
            async with self._session_factory() as session:
                await self._mark_error(session, file_id, message)
        except Exception:
            logger.exception("ingest_mark_error_failed", file_id=str(file_id))

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
        """Enqueue converted files that were never ingested into the wiki.

        A file is left converted-but-not-ingested when the app stops between
        conversion and ingestion, or when ingestion failed on a previous run.
        Files stuck mid-ingestion in PROCESSING are reset to READY first so
        ingest_source will accept them. Returns the number of files enqueued.
        """
        async with self._session_factory() as session:
            await session.execute(
                update(File)
                .where(File.status == FileStatus.PROCESSING)
                .values(status=FileStatus.READY)
            )
            await session.commit()

            ingested: set[str] = set()
            page_rows = await session.execute(select(WikiPage.source_file_ids))
            for source_ids in page_rows.scalars().all():
                if source_ids:
                    ingested.update(source_ids)

            result = await session.execute(
                select(File).where(
                    File.status == FileStatus.READY,
                    File.converted_path.is_not(None),
                )
            )
            candidates = [f for f in result.scalars().all() if str(f.id) not in ingested]

        count = 0
        for f in candidates:
            if await self.enqueue(f.class_id, f.id):
                count += 1

        if count:
            logger.info("ingest_queue_recovered", count=count)
        return count


_queue: IngestionQueue | None = None


def get_ingestion_queue() -> IngestionQueue:
    """Return the process-wide ingestion queue, creating it on first use.

    The session factory is imported lazily so importing this module does not
    pull in the database engine.
    """
    global _queue
    if _queue is None:
        from app.database import async_session_factory

        _queue = IngestionQueue(async_session_factory)
    return _queue
