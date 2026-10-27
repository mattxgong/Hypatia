"""Fixes from the project review: lint citations, crash-safe rebuild, duplicate
names and imports, cancelled generation, /ask follow-ups, history and revert,
export cleanup, queue pruning."""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_session
from app.main import app
from app.models.db_models import (
    Base,
    ChatMessage,
    Class,
    Deck,
    File,
    FileStatus,
    FileType,
    StudyMethod,
    WikiCategory,
    WikiPage,
)
from app.services import storage_service, wiki_engine
from app.services.ingestion_queue import ClassQueue, IngestionQueue, QueueItemStatus
from app.services.task_manager import task_manager
from app.services.wiki_search import ensure_fts_index


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_fts_index(engine)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def client(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    async def override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _page(class_id: uuid.UUID, path: str, content: str, **kw: object) -> WikiPage:
    return WikiPage(
        class_id=class_id,
        path=path,
        title=Path(path).stem,
        category=kw.pop("category", WikiCategory.CONCEPT),
        content=content,
        **kw,
    )


# ---------------------------------------------------------------------------
# /lint
# ---------------------------------------------------------------------------


async def test_lint_accepts_citations_by_id_encoded_name_and_link_syntax(
    session_factory: async_sessionmaker[AsyncSession],
):
    class_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(Class(id=class_id, name="Lint"))
        record = File(
            class_id=class_id,
            original_filename="lecture notes.pdf",
            file_type=FileType.PDF,
            file_size_bytes=1,
            raw_path="raw.pdf",
            status=FileStatus.READY,
        )
        session.add(record)
        await session.flush()
        session.add(
            _page(
                class_id,
                "pages/concepts/a.md",
                f"[a](hypatia://cite?file=lecture%20notes.pdf) "
                f"[b](hypatia://cite?file={record.id}&page=2) "
                f"[c](hypatia://cite?file=gone.pdf)",
            )
        )
        await session.commit()

        result = await wiki_engine.handle_lint(session, class_id)

    dead = [i.description for i in result.issues if i.issue_type == "dead_citation"]
    assert len(dead) == 1 and "gone.pdf" in dead[0]


# ---------------------------------------------------------------------------
# Crash-safe /rebuild
# ---------------------------------------------------------------------------


async def test_rebuild_interrupted_after_deleting_pages_is_recovered_at_startup(
    session_factory: async_sessionmaker[AsyncSession],
):
    class_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(Class(id=class_id, name="Crash"))
        page = _page(class_id, "pages/concepts/a.md", "Old text.", source_file_ids=["f1"])
        session.add(page)
        await session.commit()
        backup = wiki_engine._PageBackup.capture(page)

        # What a rebuild has done when it crashes: backup written, page deleted.
        wiki_engine._write_rebuild_backup(str(class_id), [backup])
        await session.delete(page)
        await session.commit()

        assert await wiki_engine.recover_interrupted_rebuilds(session) == [str(class_id)]
        restored = (
            await session.execute(select(WikiPage).where(WikiPage.class_id == class_id))
        ).scalar_one()

    assert restored.content == "Old text."
    assert restored.source_file_ids == ["f1"]
    assert not wiki_engine._rebuild_backup_path(str(class_id)).exists()


async def test_finished_rebuild_leaves_no_backup(session_factory, tmp_path: Path):
    class_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(Class(id=class_id, name="Done"))
        session.add(_page(class_id, "pages/concepts/a.md", "Text."))
        await session.commit()
        await wiki_engine.handle_rebuild(session, class_id)

    assert not wiki_engine._rebuild_backup_path(str(class_id)).exists()


# ---------------------------------------------------------------------------
# Class names and imports
# ---------------------------------------------------------------------------


async def test_duplicate_class_name_is_a_409(client: AsyncClient):
    assert (await client.post("/api/classes", json={"name": "Biology"})).status_code == 201
    dup = await client.post("/api/classes", json={"name": "Biology"})
    assert dup.status_code == 409 and "already exists" in dup.json()["detail"]

    other = (await client.post("/api/classes", json={"name": "Chemistry"})).json()
    renamed = await client.put(f"/api/classes/{other['id']}", json={"name": "Biology"})
    assert renamed.status_code == 409


def _backup(manifest: dict, entries: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        for name, data in (entries or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


async def test_import_next_to_the_original_makes_a_copy_with_its_history(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
):
    await client.post("/api/classes", json={"name": "Biology"})
    old_file_id = uuid.uuid4()
    stamp = "2025-02-03T04:05:06+00:00"
    manifest = {
        "version": 1,
        "class": {"name": "Biology", "description": None, "created_at": stamp},
        "files": [
            {
                "id": str(old_file_id),
                "original_filename": "notes.md",
                "file_type": "markdown",
                "file_size_bytes": 4,
                "raw_path": "raw/notes.md",
                "converted_path": f"converted/{old_file_id}.md",
                "status": "ready",
                "created_at": stamp,
                "updated_at": stamp,
            }
        ],
        "wiki_pages": [],
        "chat_messages": [
            {
                "id": str(uuid.uuid4()),
                "role": "user",
                "content": "hi",
                "created_at": stamp,
                "updated_at": stamp,
            }
        ],
    }
    archive = _backup(
        manifest,
        {
            "raw/notes.md": b"text",
            f"converted/{old_file_id}.md": b"# notes",
            f"converted/{old_file_id}.summary.md": b"summary",
        },
    )

    resp = await client.post(
        "/api/classes/import", files={"file": ("b.zip", archive, "application/zip")}
    )

    assert resp.status_code == 201
    assert resp.json()["name"] == "Biology (imported)"
    class_id = uuid.UUID(resp.json()["id"])
    async with session_factory() as session:
        record = (await session.execute(select(File).where(File.class_id == class_id))).scalar_one()
        message = (
            await session.execute(select(ChatMessage).where(ChatMessage.class_id == class_id))
        ).scalar_one()
        imported = await session.get(Class, class_id)
    assert imported is not None and imported.created_at == datetime(2025, 2, 3, 4, 5, 6, tzinfo=UTC)
    assert record.created_at == datetime(2025, 2, 3, 4, 5, 6, tzinfo=UTC)
    assert message.created_at == datetime(2025, 2, 3, 4, 5, 6, tzinfo=UTC)
    converted = storage_service.class_dir(str(class_id)) / "converted"
    assert Path(record.converted_path or "").name == f"{record.id}.md"
    assert sorted(p.name for p in converted.iterdir()) == [
        f"{record.id}.md",
        f"{record.id}.summary.md",
    ]


# ---------------------------------------------------------------------------
# Study generation cancelled while saving
# ---------------------------------------------------------------------------


async def test_generation_cancelled_while_saving_keeps_no_deck(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
):
    from app import database
    from app.models.schemas import DeckGenerateRequest
    from app.services.study import jobs

    class_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(Class(id=class_id, name="Study"))
        await session.commit()
    monkeypatch.setattr(database, "async_session_factory", session_factory)
    task_id = task_manager.start_task("flashcards", str(class_id))

    async def save_then_cancelled(session, cid, request, tid):  # type: ignore[no-untyped-def]
        deck = Deck(class_id=cid, name="D", generation_method=StudyMethod.LLM)
        session.add(deck)
        await session.commit()
        task_manager.cancel_task(tid)  # the user pressed Cancel just now
        return deck

    with patch.object(jobs.service, "generate_deck_with_llm", save_then_cancelled):
        await jobs._run("deck", class_id, DeckGenerateRequest(method="llm"), task_id)

    async with session_factory() as session:
        decks = (await session.execute(select(Deck).where(Deck.class_id == class_id))).all()
    assert decks == []
    assert task_manager.get_status(task_id).status == "cancelled"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# /ask follow-ups
# ---------------------------------------------------------------------------


async def test_ask_sees_the_conversation_and_reports_its_pages(
    session_factory: async_sessionmaker[AsyncSession],
):
    class_id = uuid.uuid4()
    async with session_factory() as session:
        page = _page(class_id, "pages/concepts/entropy.md", "Entropy measures disorder.")
        session.add(page)
        await session.flush()
        await wiki_engine.index_page_for_search(session, page)
        await session.commit()

        provider = AsyncMock()
        prompts: list[str] = []

        async def stream(system: str, user: str, **kwargs: object):  # type: ignore[no-untyped-def]
            prompts.append(user)
            yield "It increases."

        provider.stream = stream
        consulted: list[str] = []
        with patch("app.services.wiki_engine.get_llm_provider", return_value=provider):
            chunks = [
                c
                async for c in wiki_engine.handle_ask_stream(
                    session,
                    class_id,
                    "what happens to it over time?",
                    history=[("user", "what is entropy?"), ("assistant", "Disorder.")],
                    consulted=consulted,
                )
            ]

    assert chunks == ["It increases."]
    assert consulted == ["pages/concepts/entropy.md"]
    assert "Earlier in this conversation" in prompts[0]
    assert "Student: what is entropy?" in prompts[0]


# ---------------------------------------------------------------------------
# History, revert, export
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sha", ["--output=x", "HEAD", "zzzzzzz", "abc"])
async def test_revert_rejects_anything_but_a_commit_hash(client: AsyncClient, sha: str):
    resp = await client.post(f"/api/classes/{uuid.uuid4()}/wiki/revert", json={"commit_sha": sha})
    assert resp.status_code == 422


async def test_revert_of_unknown_commit_is_404(client: AsyncClient):
    resp = await client.post(
        f"/api/classes/{uuid.uuid4()}/wiki/revert", json={"commit_sha": "a" * 40}
    )
    assert resp.status_code == 404


async def test_downloaded_export_is_not_kept(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
):
    class_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(_page(class_id, "pages/concepts/a.md", "Text."))
        await session.commit()

    resp = await client.post(f"/api/classes/{class_id}/wiki/export")

    assert resp.status_code == 200
    from app.config import settings

    assert list((settings.data_dir / "exports" / str(class_id)).glob("*.zip")) == []


# ---------------------------------------------------------------------------
# In-memory bookkeeping stays bounded
# ---------------------------------------------------------------------------


async def test_queue_keeps_only_recent_finished_items():
    queue = IngestionQueue(AsyncMock())
    class_id = uuid.uuid4()
    queue._queues[class_id] = ClassQueue(processing=True)  # no worker in this test
    for _ in range(80):
        item = queue._enqueue_locked(class_id, uuid.uuid4())
        assert item is not None
        item.status = QueueItemStatus.COMPLETE
    queue._enqueue_locked(class_id, uuid.uuid4())

    items = queue._queues[class_id].items
    assert sum(i.status == QueueItemStatus.COMPLETE for i in items) == 50
    assert items[-1].status == QueueItemStatus.PENDING
