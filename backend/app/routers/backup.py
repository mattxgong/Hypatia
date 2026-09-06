"""Class backup/import endpoints (Task 4.8)."""

from __future__ import annotations

import json
import shutil
import stat
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models.db_models import (
    ChatMessage,
    ChatRole,
    Class,
    FileStatus,
    FileType,
    WikiCategory,
    WikiPage,
)
from app.models.db_models import (
    File as FileRecord,
)
from app.services import storage_service
from app.services.wiki_git import init_wiki_repo
from app.utils.logging import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/classes", tags=["backup"])

_MANIFEST_FILENAME = "manifest.json"
_BACKUP_VERSION = 1
_MAX_ARCHIVE_ENTRIES = 10_000
_MAX_MANIFEST_SIZE_BYTES = 10 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 500
_ARCHIVE_ROOTS = {"raw", "converted", "wiki", "thumbnails"}


class _ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ClassManifest(_ManifestModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    created_at: datetime | None = None


class _FileManifest(_ManifestModel):
    id: uuid.UUID
    original_filename: str = Field(min_length=1, max_length=255)
    file_type: FileType
    file_size_bytes: int = Field(ge=0)
    raw_path: str = Field(min_length=1, max_length=1024)
    converted_path: str | None = Field(default=None, max_length=1024)
    status: FileStatus
    error_message: str | None = None
    metadata_json: dict[str, object] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class _WikiPageManifest(_ManifestModel):
    id: uuid.UUID
    path: str = Field(min_length=1, max_length=1024)
    title: str = Field(min_length=1, max_length=255)
    category: WikiCategory
    content: str
    source_file_ids: list[uuid.UUID] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class _ChatMessageManifest(_ManifestModel):
    id: uuid.UUID
    role: ChatRole
    content: str
    command: str | None = Field(default=None, max_length=64)
    metadata_json: dict[str, object] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class _BackupManifest(_ManifestModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version: Literal[1]
    class_info: _ClassManifest = Field(alias="class")
    files: list[_FileManifest] = Field(default_factory=list, max_length=_MAX_ARCHIVE_ENTRIES)
    wiki_pages: list[_WikiPageManifest] = Field(
        default_factory=list, max_length=_MAX_ARCHIVE_ENTRIES
    )
    chat_messages: list[_ChatMessageManifest] = Field(
        default_factory=list, max_length=_MAX_ARCHIVE_ENTRIES
    )


def _invalid_backup(detail: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(status_code=status_code, detail=f"Invalid backup: {detail}")


def _archive_path(info: zipfile.ZipInfo) -> PurePosixPath:
    name = info.filename
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.parts[0] not in _ARCHIVE_ROOTS
    ):
        raise _invalid_backup(f"unsafe archive path {name!r}")

    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise _invalid_backup(f"symbolic links are not allowed ({name!r})")
    return path


def _inspect_archive(zf: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    infos = zf.infolist()
    if len(infos) > _MAX_ARCHIVE_ENTRIES:
        raise _invalid_backup("too many archive entries", status.HTTP_413_CONTENT_TOO_LARGE)
    if _MANIFEST_FILENAME not in {info.filename for info in infos}:
        raise _invalid_backup("missing manifest.json")

    seen_names: set[str] = set()
    expanded_size = 0
    entries: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    for info in infos:
        normalized_name = info.filename.casefold()
        if normalized_name in seen_names:
            raise _invalid_backup(f"duplicate archive path {info.filename!r}")
        seen_names.add(normalized_name)

        expanded_size += info.file_size
        if expanded_size > settings.max_upload_size_bytes:
            raise _invalid_backup(
                "expanded archive exceeds the configured size limit",
                status.HTTP_413_CONTENT_TOO_LARGE,
            )
        if (
            info.file_size > 1024 * 1024
            and info.file_size / max(info.compress_size, 1) > _MAX_COMPRESSION_RATIO
        ):
            raise _invalid_backup(
                f"archive entry has an unsafe compression ratio ({info.filename!r})",
                status.HTTP_413_CONTENT_TOO_LARGE,
            )

        if info.filename == _MANIFEST_FILENAME:
            if info.file_size > _MAX_MANIFEST_SIZE_BYTES:
                raise _invalid_backup(
                    "manifest exceeds the size limit",
                    status.HTTP_413_CONTENT_TOO_LARGE,
                )
            continue
        entries.append((info, _archive_path(info)))

    return entries


def _extract_archive(
    zf: zipfile.ZipFile,
    entries: list[tuple[zipfile.ZipInfo, PurePosixPath]],
    stage_root: Path,
) -> None:
    for subdir in _ARCHIVE_ROOTS:
        (stage_root / subdir).mkdir(parents=True, exist_ok=True)

    for info, relative_path in entries:
        target = stage_root.joinpath(*relative_path.parts)
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as source, target.open("wb") as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)


def _restored_path(
    stage_root: Path,
    final_root: Path,
    relative_path: str,
    expected_root: str,
) -> str:
    path = PurePosixPath(relative_path.replace("\\", "/"))
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or not path.parts
        or path.parts[0] != expected_root
    ):
        raise _invalid_backup(f"unsafe manifest path {relative_path!r}")
    if not stage_root.joinpath(*path.parts).is_file():
        raise _invalid_backup(f"referenced file is missing ({relative_path!r})")
    return str(final_root.joinpath(*path.parts))


def _serialize_file(f: FileRecord, class_root: Path) -> dict:
    raw_rel = Path(f.raw_path).relative_to(class_root).as_posix() if f.raw_path else None
    conv_rel = (
        Path(f.converted_path).relative_to(class_root).as_posix() if f.converted_path else None
    )
    return {
        "id": str(f.id),
        "original_filename": f.original_filename,
        "file_type": f.file_type.value,
        "file_size_bytes": f.file_size_bytes,
        "raw_path": raw_rel,
        "converted_path": conv_rel,
        "status": f.status.value,
        "error_message": f.error_message,
        "metadata_json": f.metadata_json,
        "created_at": f.created_at.isoformat(),
        "updated_at": f.updated_at.isoformat(),
    }


def _serialize_wiki_page(p: WikiPage) -> dict:
    return {
        "id": str(p.id),
        "path": p.path,
        "title": p.title,
        "category": p.category.value,
        "content": p.content,
        "source_file_ids": p.source_file_ids,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


def _serialize_chat_message(m: ChatMessage) -> dict:
    return {
        "id": str(m.id),
        "role": m.role.value,
        "content": m.content,
        "command": m.command,
        "metadata_json": m.metadata_json,
        "created_at": m.created_at.isoformat(),
        "updated_at": m.updated_at.isoformat(),
    }


@router.post("/{class_id}/backup")
async def backup_class(
    class_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> FileResponse:
    class_ = await session.get(Class, class_id)
    if class_ is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")

    class_root = storage_service.class_dir(str(class_id))
    if not class_root.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Class directory not found"
        )

    files_result = await session.execute(select(FileRecord).where(FileRecord.class_id == class_id))
    pages_result = await session.execute(select(WikiPage).where(WikiPage.class_id == class_id))
    messages_result = await session.execute(
        select(ChatMessage).where(ChatMessage.class_id == class_id)
    )

    files = files_result.scalars().all()
    pages = pages_result.scalars().all()
    messages = messages_result.scalars().all()

    manifest = {
        "version": _BACKUP_VERSION,
        "class": {
            "name": class_.name,
            "description": class_.description,
            "created_at": class_.created_at.isoformat(),
        },
        "files": [_serialize_file(f, class_root) for f in files],
        "wiki_pages": [_serialize_wiki_page(p) for p in pages],
        "chat_messages": [_serialize_chat_message(m) for m in messages],
    }

    tmp_dir = Path(tempfile.mkdtemp())
    zip_path = tmp_dir / f"hypatia-backup-{class_id}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(_MANIFEST_FILENAME, json.dumps(manifest, indent=2))

        for subdir in ("raw", "converted", "wiki", "thumbnails"):
            dir_path = class_root / subdir
            if dir_path.exists():
                for file_path in dir_path.rglob("*"):
                    if file_path.is_file():
                        arcname = str(file_path.relative_to(class_root))
                        zf.write(file_path, arcname)

    from starlette.background import BackgroundTask

    return FileResponse(
        zip_path,
        filename=f"hypatia-backup-{class_.name}.zip",
        media_type="application/zip",
        background=BackgroundTask(shutil.rmtree, tmp_dir, True),
    )


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_class(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload must be a .zip file",
        )

    tmp_dir = Path(tempfile.mkdtemp())
    zip_path = tmp_dir / "upload.zip"

    with zip_path.open("wb") as f:
        upload_size = 0
        while chunk := await file.read(1024 * 1024):
            upload_size += len(chunk)
            if upload_size > settings.max_upload_size_bytes:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Backup upload exceeds the configured size limit",
                )
            f.write(chunk)

    new_class_id = uuid.uuid4()
    new_class = Class(id=new_class_id, name="")
    class_root = storage_service.class_dir(str(new_class_id))
    class_directory_created = False
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            archive_entries = _inspect_archive(zf)
            try:
                manifest = _BackupManifest.model_validate_json(zf.read(_MANIFEST_FILENAME))
            except (ValidationError, ValueError) as exc:
                raise _invalid_backup("manifest validation failed") from exc

            stage_root = tmp_dir / "class"
            _extract_archive(zf, archive_entries, stage_root)

            new_class.name = manifest.class_info.name
            new_class.description = manifest.class_info.description
            session.add(new_class)

            file_id_map: dict[uuid.UUID, uuid.UUID] = {}
            for file_data in manifest.files:
                if file_data.id in file_id_map:
                    raise _invalid_backup(f"duplicate file ID {file_data.id}")
                imported_file_id = uuid.uuid4()
                file_id_map[file_data.id] = imported_file_id
                raw_path = _restored_path(
                    stage_root,
                    class_root,
                    file_data.raw_path,
                    "raw",
                )
                converted_path = (
                    _restored_path(
                        stage_root,
                        class_root,
                        file_data.converted_path,
                        "converted",
                    )
                    if file_data.converted_path
                    else None
                )
                session.add(
                    FileRecord(
                        id=imported_file_id,
                        class_id=new_class_id,
                        original_filename=file_data.original_filename,
                        file_type=file_data.file_type,
                        file_size_bytes=file_data.file_size_bytes,
                        raw_path=raw_path,
                        converted_path=converted_path,
                        status=file_data.status,
                        error_message=file_data.error_message,
                        metadata_json=file_data.metadata_json,
                    )
                )

            for page_data in manifest.wiki_pages:
                source_file_ids: list[str] = []
                for source_id in page_data.source_file_ids or []:
                    imported_source_id = file_id_map.get(source_id)
                    if imported_source_id is None:
                        raise _invalid_backup(f"unknown source file ID {source_id}")
                    source_file_ids.append(str(imported_source_id))
                session.add(
                    WikiPage(
                        class_id=new_class_id,
                        path=page_data.path,
                        title=page_data.title,
                        category=page_data.category,
                        content=page_data.content,
                        source_file_ids=source_file_ids or None,
                    )
                )

            for msg_data in manifest.chat_messages:
                session.add(
                    ChatMessage(
                        class_id=new_class_id,
                        role=msg_data.role,
                        content=msg_data.content,
                        command=msg_data.command,
                        metadata_json=msg_data.metadata_json,
                    )
                )

            await session.flush()
            class_root.parent.mkdir(parents=True, exist_ok=True)
            stage_root.replace(class_root)
            class_directory_created = True
            init_wiki_repo(str(new_class_id))
            await session.commit()

    except HTTPException:
        await session.rollback()
        if class_directory_created:
            storage_service.delete_class_directory(str(new_class_id))
        raise
    except IntegrityError as exc:
        await session.rollback()
        if class_directory_created:
            storage_service.delete_class_directory(str(new_class_id))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A class with this name already exists",
        ) from exc
    except zipfile.BadZipFile as exc:
        await session.rollback()
        if class_directory_created:
            storage_service.delete_class_directory(str(new_class_id))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ZIP file"
        ) from exc
    except Exception:
        await session.rollback()
        if class_directory_created:
            storage_service.delete_class_directory(str(new_class_id))
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    logger.info("class_imported", class_id=str(new_class_id), name=new_class.name)
    return {
        "id": str(new_class_id),
        "name": new_class.name,
        "file_count": len(manifest.files),
        "page_count": len(manifest.wiki_pages),
        "message_count": len(manifest.chat_messages),
    }
