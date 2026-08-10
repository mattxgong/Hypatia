"""Task 2.9 acceptance: file upload/list/status-poll router."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import get_session
from app.main import app
from app.models.db_models import Base, Class, File, FileStatus, FileType
from app.routers import files as files_router
from app.services.file_converter import ProcessingResult


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


async def _make_class(
    session_factory: async_sessionmaker[AsyncSession], name: str = "Test Class"
) -> UUID:
    async with session_factory() as session:
        class_ = Class(name=name)
        session.add(class_)
        await session.commit()
        return class_.id


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(files_router, "async_session_factory", session_factory)
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_upload_dispatches_processing_and_creates_pending_record(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    class_id = await _make_class(session_factory)
    fake_result = ProcessingResult(success=True, converted_path=Path("ignored.md"))

    with patch.object(
        files_router, "process_file", AsyncMock(return_value=fake_result)
    ) as process_file_mock:
        response = await client.post(
            f"/api/classes/{class_id}/files",
            files=[("files", ("notes.txt", b"hello world", "text/plain"))],
        )

    assert response.status_code == 202
    body = response.json()
    assert len(body) == 1
    assert body[0]["original_filename"] == "notes.txt"
    assert body[0]["class_id"] == str(class_id)
    assert body[0]["status"] == "pending"
    process_file_mock.assert_called_once()

    async with session_factory() as session:
        result = await session.execute(select(File).where(File.class_id == class_id))
        file_ = result.scalar_one()
        assert file_.file_type == FileType.MARKDOWN
        assert file_.file_size_bytes == len(b"hello world")
        assert Path(file_.raw_path).exists()


async def test_upload_full_pipeline_marks_file_ready(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    class_id = await _make_class(session_factory)

    response = await client.post(
        f"/api/classes/{class_id}/files",
        files=[("files", ("notes.txt", b"hello world", "text/plain"))],
    )

    assert response.status_code == 202
    file_id = response.json()[0]["id"]

    status_response = await client.get(f"/api/classes/{class_id}/files/{file_id}")

    assert status_response.status_code == 200
    body = status_response.json()
    assert body["status"] == "ready"
    assert body["converted_path"] is not None
    assert Path(body["converted_path"]).exists()


async def test_upload_rejects_oversized_file(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_upload_size_bytes", 5)
    class_id = UUID("00000000-0000-0000-0000-000000000000")

    response = await client.post(
        f"/api/classes/{class_id}/files",
        files=[("files", ("notes.txt", b"this is too long", "text/plain"))],
    )

    assert response.status_code == 413


async def test_upload_rejects_degenerate_filename(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    class_id = await _make_class(session_factory)

    response = await client.post(
        f"/api/classes/{class_id}/files",
        files=[("files", ("..", b"hello", "text/plain"))],
    )

    assert response.status_code == 400


async def test_upload_sanitizes_path_traversal_filename(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    class_id = await _make_class(session_factory)
    fake_result = ProcessingResult(success=True, converted_path=Path("ignored.md"))

    with patch.object(files_router, "process_file", AsyncMock(return_value=fake_result)):
        response = await client.post(
            f"/api/classes/{class_id}/files",
            files=[("files", ("../../etc/passwd", b"hello", "text/plain"))],
        )

    assert response.status_code == 202

    async with session_factory() as session:
        result = await session.execute(select(File).where(File.class_id == class_id))
        file_ = result.scalar_one()
        assert Path(file_.raw_path).name == "passwd"
        assert Path(file_.raw_path).parent.name == "raw"
        assert Path(file_.raw_path).exists()


async def test_list_files_returns_all_files_for_class(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    class_id = await _make_class(session_factory)
    async with session_factory() as session:
        session.add(
            File(
                class_id=class_id,
                original_filename="a.pdf",
                file_type=FileType.PDF,
                file_size_bytes=10,
                raw_path="raw/a.pdf",
                status=FileStatus.PENDING,
            )
        )
        session.add(
            File(
                class_id=class_id,
                original_filename="b.pdf",
                file_type=FileType.PDF,
                file_size_bytes=20,
                raw_path="raw/b.pdf",
                status=FileStatus.READY,
            )
        )
        await session.commit()

    response = await client.get(f"/api/classes/{class_id}/files")

    assert response.status_code == 200
    names = {item["original_filename"] for item in response.json()}
    assert names == {"a.pdf", "b.pdf"}


async def test_get_file_returns_404_for_unknown_file(client: AsyncClient) -> None:
    class_id = UUID("00000000-0000-0000-0000-000000000000")
    file_id = UUID("11111111-1111-1111-1111-111111111111")

    response = await client.get(f"/api/classes/{class_id}/files/{file_id}")

    assert response.status_code == 404


async def test_get_file_returns_404_when_class_id_mismatches(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    class_id = await _make_class(session_factory)
    other_class_id = await _make_class(session_factory, name="Other Class")
    async with session_factory() as session:
        file_ = File(
            class_id=class_id,
            original_filename="a.pdf",
            file_type=FileType.PDF,
            file_size_bytes=10,
            raw_path="raw/a.pdf",
            status=FileStatus.PENDING,
        )
        session.add(file_)
        await session.commit()
        file_id = file_.id

    response = await client.get(f"/api/classes/{other_class_id}/files/{file_id}")

    assert response.status_code == 404
