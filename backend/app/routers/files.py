"""File upload/list/status/serving endpoints (Tasks 2.9, 4.3)."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory, get_session
from app.models.db_models import File as FileRecord
from app.models.db_models import FileStatus
from app.models.schemas import FileRead, FileUploadResponse
from app.services import storage_service
from app.services.file_converter import classify_file_type, process_file
from app.utils.logging import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/classes/{class_id}/files", tags=["files"])

_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MiB, keeps memory bounded regardless of file size


async def _process_file_background(file_id: uuid.UUID, raw_path: Path, output_path: Path) -> None:
    """Run process_file with its own DB session, since the request-scoped
    session is closed by the time a background task actually runs."""
    async with async_session_factory() as session:
        await process_file(session, file_id, raw_path, output_path)


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
    responses: list[FileUploadResponse] = []

    for upload in files:
        filename = upload.filename or "upload"
        try:
            raw_path = storage_service.resolve_raw_path(str(class_id), filename)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        file_size_bytes = await _stream_upload_to_disk(upload, raw_path)

        file_ = FileRecord(
            class_id=class_id,
            original_filename=filename,
            file_type=classify_file_type(filename),
            file_size_bytes=file_size_bytes,
            raw_path=str(raw_path),
            status=FileStatus.PENDING,
        )
        session.add(file_)
        await session.commit()
        await session.refresh(file_)

        output_path = storage_service.get_converted_path(str(class_id), f"{Path(filename).stem}.md")
        background_tasks.add_task(_process_file_background, file_.id, raw_path, output_path)
        logger.info("file_upload_accepted", class_id=str(class_id), file_id=str(file_.id))

        responses.append(FileUploadResponse.model_validate(file_))

    return responses


@router.get("", response_model=list[FileRead])
async def list_files(
    class_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[FileRead]:
    result = await session.execute(select(FileRecord).where(FileRecord.class_id == class_id))
    return [FileRead.model_validate(file_) for file_ in result.scalars().all()]


@router.get("/{file_id}", response_model=FileRead)
async def get_file(
    class_id: uuid.UUID, file_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> FileRead:
    file_ = await session.get(FileRecord, file_id)
    if file_ is None or file_.class_id != class_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileRead.model_validate(file_)


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

    raw_path = Path(file_.raw_path)
    if raw_path.exists():
        raw_path.unlink()
    if file_.converted_path:
        converted_path = Path(file_.converted_path)
        if converted_path.exists():
            converted_path.unlink()

    await session.delete(file_)
    await session.commit()
    logger.info("file_deleted", class_id=str(class_id), file_id=str(file_id))
