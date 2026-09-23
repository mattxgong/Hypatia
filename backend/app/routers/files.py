"""File upload/list/status/serving endpoints (Tasks 2.9, 4.3)."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory, get_session
from app.models.db_models import File as FileRecord
from app.models.db_models import FileStatus
from app.models.schemas import FileRead, FileUploadResponse
from app.services import storage_service
from app.services.file_converter import classify_file_type, process_file
from app.services.ingestion_queue import get_ingestion_queue
from app.services.task_manager import task_manager
from app.utils.logging import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/classes/{class_id}/files", tags=["files"])

_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MiB, keeps memory bounded regardless of file size


async def _convert_file(
    class_id: uuid.UUID, file_id: uuid.UUID, filename: str, raw_path: Path, output_path: Path
) -> bool:
    task_id = task_manager.start_task("convert", str(class_id))
    task_manager.update_progress(task_id, 0, f"Converting {filename}")
    try:
        async with async_session_factory() as session:
            result = await process_file(session, file_id, raw_path, output_path)
    except asyncio.CancelledError:
        task_manager.cancel_task(task_id)
        raise
    except Exception as exc:
        task_manager.fail_task(task_id, str(exc))
        raise
    if result.success:
        task_manager.complete_task(task_id)
    else:
        logger.warning("file_conversion_failed", file_id=str(file_id), error=result.error)
        task_manager.fail_task(task_id, result.error or "Conversion failed")
    return result.success


async def _process_file_background(
    class_id: uuid.UUID, file_id: uuid.UUID, filename: str, raw_path: Path, output_path: Path
) -> None:
    """Convert an uploaded file, then queue it for wiki ingestion.

    Uses its own DB session, since the request-scoped session is closed by the
    time a background task actually runs. The queue owns the conversion so that
    deleting the file cancels it, and ingests files for one Class one at a time.
    """
    await get_ingestion_queue().convert_and_enqueue(
        class_id, file_id, _convert_file(class_id, file_id, filename, raw_path, output_path)
    )


def _duplicate_filenames(names: set[str]) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"A file named {', '.join(sorted(names))} already exists in this class. "
            "Rename the file or remove the existing one first."
        ),
    )


async def _stream_upload_to_disk(upload: UploadFile, path: Path) -> int:
    """Write upload's contents to path in bounded chunks, so at most one
    chunk is held in memory regardless of file size. Aborts and deletes the
    partial file, raising HTTP 413, if the running total exceeds
    settings.max_upload_size_bytes before the stream ends. Returns the
    total bytes written."""
    total = 0
    exceeded = False
    with path.open("wb") as f:
        while chunk := await upload.read(_UPLOAD_CHUNK_SIZE):
            total += len(chunk)
            if total > settings.max_upload_size_bytes:
                exceeded = True
                break
            f.write(chunk)

    if exceeded:
        path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"{upload.filename} exceeds the {settings.max_upload_size_bytes} byte upload limit"
            ),
        )
    return total


@router.post("", response_model=list[FileUploadResponse], status_code=status.HTTP_202_ACCEPTED)
async def upload_files(
    class_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_session),
) -> list[FileUploadResponse]:
    try:
        filenames = [
            storage_service.sanitize_filename(upload.filename or "upload") for upload in files
        ]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    existing = await session.execute(
        select(FileRecord.original_filename).where(
            FileRecord.class_id == class_id, FileRecord.original_filename.in_(filenames)
        )
    )
    duplicates = set(existing.scalars().all())
    duplicates.update(name for name in filenames if filenames.count(name) > 1)
    if duplicates:
        raise _duplicate_filenames(duplicates)

    # Background tasks only run on success, so a failure part-way through a
    # batch must not leave earlier files stranded as PENDING.
    records: list[FileRecord] = []
    try:
        for upload, filename in zip(files, filenames, strict=True):
            raw_path = storage_service.resolve_raw_path(str(class_id), filename)
            file_ = FileRecord(
                id=uuid.uuid4(),
                class_id=class_id,
                original_filename=filename,
                file_type=classify_file_type(filename),
                file_size_bytes=0,
                raw_path=str(raw_path),
                status=FileStatus.PENDING,
            )
            records.append(file_)
            file_.file_size_bytes = await _stream_upload_to_disk(upload, raw_path)
        session.add_all(records)
        await session.commit()
    except (HTTPException, IntegrityError) as exc:
        await session.rollback()
        for file_ in records:
            Path(file_.raw_path).unlink(missing_ok=True)
        if isinstance(exc, IntegrityError):
            raise _duplicate_filenames(set(filenames)) from exc
        raise

    responses: list[FileUploadResponse] = []
    for file_ in records:
        await session.refresh(file_)
        output_path = storage_service.converted_output_path(str(class_id), file_.id)
        background_tasks.add_task(
            _process_file_background,
            class_id,
            file_.id,
            file_.original_filename,
            Path(file_.raw_path),
            output_path,
        )
        logger.info("file_upload_accepted", class_id=str(class_id), file_id=str(file_.id))
        responses.append(FileUploadResponse.model_validate(file_))

    return responses


def _file_read(file_: FileRecord) -> FileRead:
    ingesting = get_ingestion_queue().is_ingesting(file_.class_id, file_.id)
    return FileRead.model_validate(file_).model_copy(update={"ingesting": ingesting})


@router.get("", response_model=list[FileRead])
async def list_files(
    class_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[FileRead]:
    result = await session.execute(select(FileRecord).where(FileRecord.class_id == class_id))
    return [_file_read(file_) for file_ in result.scalars().all()]


@router.get("/{file_id}", response_model=FileRead)
async def get_file(
    class_id: uuid.UUID, file_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> FileRead:
    file_ = await session.get(FileRecord, file_id)
    if file_ is None or file_.class_id != class_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return _file_read(file_)


@router.get("/{file_id}/raw")
async def get_file_raw(
    class_id: uuid.UUID, file_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> FileResponse:
    file_ = await session.get(FileRecord, file_id)
    if file_ is None or file_.class_id != class_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    raw_path = Path(file_.raw_path)
    if not raw_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Raw file missing")
    return FileResponse(raw_path, filename=file_.original_filename)


@router.get("/{file_id}/converted")
async def get_file_converted(
    class_id: uuid.UUID, file_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> FileResponse:
    file_ = await session.get(FileRecord, file_id)
    if file_ is None or file_.class_id != class_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if not file_.converted_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No converted file available"
        )
    converted_path = Path(file_.converted_path)
    if not converted_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Converted file missing")
    return FileResponse(converted_path, filename=f"{Path(file_.original_filename).stem}.md")


@router.get("/{file_id}/open")
async def open_file_with_location(
    class_id: uuid.UUID,
    file_id: uuid.UUID,
    loc: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    file_ = await session.get(FileRecord, file_id)
    if file_ is None or file_.class_id != class_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    raw_path = Path(file_.raw_path)
    if not raw_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Raw file missing")
    response = FileResponse(raw_path, filename=file_.original_filename)
    if loc:
        response.headers["X-Location"] = loc
    return response


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    class_id: uuid.UUID, file_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> None:
    file_ = await session.get(FileRecord, file_id)
    if file_ is None or file_.class_id != class_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    from app.services.wiki_engine import handle_remove

    await handle_remove(session, class_id, file_.original_filename)
    logger.info("file_deleted", class_id=str(class_id), file_id=str(file_id))
