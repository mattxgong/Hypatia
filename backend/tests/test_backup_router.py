"""Tests for Class backup/import endpoints (Task 4.8)."""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import get_session
from app.main import app
from app.models.db_models import (
    Base,
    ChatMessage,
    ChatRole,
    Class,
    FileStatus,
    FileType,
    WikiCategory,
    WikiPage,
)
from app.models.db_models import File as FileRecord


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class TestBackup:
    async def test_backup_not_found(self, client: AsyncClient) -> None:
        resp = await client.post(f"/api/classes/{uuid.uuid4()}/backup")
        assert resp.status_code == 404

    async def test_backup_creates_zip(
        self,
        client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        tmp_path: Path,
    ) -> None:
        class_id = uuid.uuid4()
        class_dir = tmp_path / "classes" / str(class_id)
        class_dir.mkdir(parents=True)
        (class_dir / "raw").mkdir()
        (class_dir / "raw" / "note.md").write_text("# Hello")

        async with session_factory() as session:
            session.add(Class(id=class_id, name="Test Class"))
            await session.flush()
            session.add(
                FileRecord(
                    class_id=class_id,
                    original_filename="note.md",
                    file_type=FileType.MARKDOWN,
                    file_size_bytes=7,
                    raw_path=str(class_dir / "raw" / "note.md"),
                    status=FileStatus.READY,
                )
            )
            session.add(
                WikiPage(
                    class_id=class_id,
                    path="index.md",
                    title="Index",
                    category=WikiCategory.INDEX,
                    content="# Index",
                )
            )
            session.add(
                ChatMessage(
                    class_id=class_id,
                    role=ChatRole.USER,
                    content="Hello",
                )
            )
            await session.commit()

        resp = await client.post(f"/api/classes/{class_id}/backup")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf, "r") as zf:
            assert "manifest.json" in zf.namelist()
            assert "raw/note.md" in zf.namelist()
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["class"]["name"] == "Test Class"
            assert len(manifest["files"]) == 1
            assert len(manifest["wiki_pages"]) == 1
            assert len(manifest["chat_messages"]) == 1


class TestImport:
    async def test_import_requires_zip(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/classes/import",
            files={"file": ("backup.txt", b"not a zip", "text/plain")},
        )
        assert resp.status_code == 400

    async def test_import_rejects_bad_zip(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/classes/import",
            files={"file": ("backup.zip", b"not a zip", "application/zip")},
        )
        assert resp.status_code == 400

    async def test_import_rejects_missing_manifest(self, client: AsyncClient) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("other.txt", "hello")
        buf.seek(0)

        resp = await client.post(
            "/api/classes/import",
            files={"file": ("backup.zip", buf.getvalue(), "application/zip")},
        )
        assert resp.status_code == 400
        assert "manifest" in resp.json()["detail"].lower()

    async def test_import_creates_class(self, client: AsyncClient, tmp_path: Path) -> None:
        manifest = {
            "version": 1,
            "class": {"name": "Imported Class", "description": "desc"},
            "files": [
                {
                    "id": str(uuid.uuid4()),
                    "original_filename": "doc.md",
                    "file_type": "markdown",
                    "file_size_bytes": 10,
                    "raw_path": "raw/doc.md",
                    "converted_path": None,
                    "status": "ready",
                    "error_message": None,
                    "metadata_json": None,
                    "created_at": "2024-01-01T00:00:00",
                    "updated_at": "2024-01-01T00:00:00",
                }
            ],
            "wiki_pages": [
                {
                    "id": str(uuid.uuid4()),
                    "path": "index.md",
                    "title": "Index",
                    "category": "index",
                    "content": "# Index",
                    "source_file_ids": None,
                    "created_at": "2024-01-01T00:00:00",
                    "updated_at": "2024-01-01T00:00:00",
                }
            ],
            "chat_messages": [
                {
                    "id": str(uuid.uuid4()),
                    "role": "user",
                    "content": "Hello",
                    "command": None,
                    "metadata_json": None,
                    "created_at": "2024-01-01T00:00:00",
                    "updated_at": "2024-01-01T00:00:00",
                }
            ],
        }

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("raw/doc.md", "# Document")
        buf.seek(0)

        resp = await client.post(
            "/api/classes/import",
            files={"file": ("backup.zip", buf.getvalue(), "application/zip")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Imported Class"
        assert data["file_count"] == 1
        assert data["page_count"] == 1
        assert data["message_count"] == 1
        assert "id" in data
