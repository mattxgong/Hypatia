"""Class backup/import endpoints (Task 4.8)."""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


def _serialize_file(f: FileRecord, class_root: Path) -> dict:
    raw_rel = str(Path(f.raw_path).relative_to(class_root)) if f.raw_path else None
    conv_rel = str(Path(f.converted_path).relative_to(class_root)) if f.converted_path else None
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
        "version": 1,
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
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload must be a .zip file",
        )

    tmp_dir = Path(tempfile.mkdtemp())
    zip_path = tmp_dir / "upload.zip"

    with zip_path.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if _MANIFEST_FILENAME not in zf.namelist():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid backup: missing manifest.json",
                )

            manifest = json.loads(zf.read(_MANIFEST_FILENAME))

            new_class = Class(
                name=manifest["class"]["name"],
                description=manifest["class"].get("description"),
            )
            session.add(new_class)
            await session.commit()
            await session.refresh(new_class)

            new_class_id = str(new_class.id)
            class_root = storage_service.create_class_directories(new_class_id)
            init_wiki_repo(new_class_id)

            for entry in zf.namelist():
                if entry == _MANIFEST_FILENAME:
                    continue
                target = (class_root / entry).resolve()
                if not str(target).startswith(str(class_root.resolve())):
                    continue
                if entry.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(entry))

            for file_data in manifest.get("files", []):
                raw_path = (
                    str(class_root / file_data["raw_path"]) if file_data.get("raw_path") else ""
                )
                conv_path = (
                    str(class_root / file_data["converted_path"])
                    if file_data.get("converted_path")
                    else None
                )
                db_file = FileRecord(
                    class_id=new_class.id,
                    original_filename=file_data["original_filename"],
                    file_type=FileType(file_data["file_type"]),
                    file_size_bytes=file_data["file_size_bytes"],
                    raw_path=raw_path,
                    converted_path=conv_path,
                    status=FileStatus(file_data["status"]),
                    error_message=file_data.get("error_message"),
                    metadata_json=file_data.get("metadata_json"),
                )
                session.add(db_file)

            for page_data in manifest.get("wiki_pages", []):
                db_page = WikiPage(
                    class_id=new_class.id,
                    path=page_data["path"],
                    title=page_data["title"],
                    category=WikiCategory(page_data["category"]),
                    content=page_data["content"],
                    source_file_ids=page_data.get("source_file_ids"),
                )
                session.add(db_page)

            for msg_data in manifest.get("chat_messages", []):
                db_msg = ChatMessage(
                    class_id=new_class.id,
                    role=ChatRole(msg_data["role"]),
                    content=msg_data["content"],
                    command=msg_data.get("command"),
                    metadata_json=msg_data.get("metadata_json"),
                )
                session.add(db_msg)

            await session.commit()

    except zipfile.BadZipFile as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ZIP file"
        ) from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    logger.info("class_imported", class_id=new_class_id, name=new_class.name)
    return {
        "id": new_class_id,
        "name": new_class.name,
        "file_count": len(manifest.get("files", [])),
        "page_count": len(manifest.get("wiki_pages", [])),
        "message_count": len(manifest.get("chat_messages", [])),
    }
