"""The database is the wiki's source of truth; disk and git mirror it.

Covers atomic ingest (nothing written on failure or cancel), the guards on
page updates, the per-Class operation lock, the disk mirror, revert, and
/remove's handling of user-edited pages.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db_models import Base, Class, File, FileStatus, FileType, WikiCategory, WikiPage
from app.services import wiki_git
from app.services.task_manager import task_manager
from app.services.wiki_engine import (
    handle_remove,
    handle_summarize,
    ingest_source,
    revert_wiki,
    update_wiki_page,
)
from app.services.wiki_search import ensure_fts_index, hybrid_search
from app.services.wiki_store import class_operation_lock, mirror_to_disk


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_fts_index(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _page_xml(path: str, title: str, body: str, action: str = "create") -> str:
    return (
        f'<wiki-page path="{path}" action="{action}">\n---\ntitle: "{title}"\n'
        f"type: concept\nsources: []\ntags: []\n---\n\n{body}\n</wiki-page>\n"
    )


async def _make_file(
    session: AsyncSession, class_id: uuid.UUID, tmp_path: Path, text: str = "# Notes\n\nText."
) -> File:
    converted = tmp_path / f"{uuid.uuid4().hex}.md"
    converted.write_text(text, encoding="utf-8")
    if await session.get(Class, class_id) is None:
        session.add(Class(id=class_id, name=f"Class {class_id.hex[:8]}"))
    record = File(
        class_id=class_id,
        original_filename=f"{converted.stem}.pdf",
        file_type=FileType.PDF,
        file_size_bytes=10,
        raw_path=str(tmp_path / "raw.pdf"),
        converted_path=str(converted),
        status=FileStatus.READY,
    )
    session.add(record)
    await session.commit()
    return record


async def _pages(session: AsyncSession, class_id: uuid.UUID) -> dict[str, WikiPage]:
    rows = (
        await session.execute(
            select(WikiPage)
            .where(WikiPage.class_id == class_id)
            .execution_options(populate_existing=True)
        )
    ).scalars()
    return {p.path: p for p in rows}


def _provider(*outputs: str | Exception) -> AsyncMock:
    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=list(outputs))
    return provider


def _page_files(class_id: uuid.UUID) -> set[str]:
    pages_dir = wiki_git.wiki_dir(str(class_id)) / "pages"
    if not pages_dir.exists():
        return set()
    return {p.relative_to(pages_dir.parent).as_posix() for p in pages_dir.rglob("*.md")}


# ---------------------------------------------------------------------------
# Atomic ingest
# ---------------------------------------------------------------------------


async def test_ingest_writes_pages_and_mirrors_them(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    record = await _make_file(db_session, class_id, tmp_path)
    provider = _provider(_page_xml("pages/concepts/a.md", "A", "About A."))

    with patch("app.services.wiki_engine.get_llm_provider", return_value=provider):
        result = await ingest_source(db_session, class_id, record.id)

    assert result.success and result.pages_created == ["pages/concepts/a.md"]
    page = (await _pages(db_session, class_id))["pages/concepts/a.md"]
    assert page.source_file_ids == [str(record.id)]
    assert _page_files(class_id) == {"pages/concepts/a.md"}
    on_disk = wiki_git.wiki_dir(str(class_id)) / "pages/concepts/a.md"
    assert on_disk.read_text(encoding="utf-8") == page.content


async def test_failed_later_chunk_writes_nothing(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    text = "\n".join(f"Line {i} about a long topic in the notes." for i in range(120))
    record = await _make_file(db_session, class_id, tmp_path, text)
    provider = _provider(
        _page_xml("pages/concepts/a.md", "A", "From chunk one."),
        RuntimeError("model went away"),
    )

    with (
        patch("app.services.wiki_engine._prompt_budget", return_value=1000),
        patch("app.services.wiki_engine.get_llm_provider", return_value=provider),
    ):
        result = await ingest_source(db_session, class_id, record.id)

    assert provider.complete.await_count == 2
    assert result.success is False
    assert await _pages(db_session, class_id) == {}
    assert _page_files(class_id) == set()


async def test_cancel_between_chunks_writes_nothing(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    text = "\n".join(f"Line {i} about a long topic in the notes." for i in range(120))
    record = await _make_file(db_session, class_id, tmp_path, text)
    task_id = task_manager.start_task("ingest", str(class_id))

    async def first_chunk_then_cancel(*args: object, **kwargs: object) -> str:
        task_manager.cancel_task(task_id)
        return _page_xml("pages/concepts/a.md", "A", "From chunk one.")

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=first_chunk_then_cancel)

    with (
        patch("app.services.wiki_engine._prompt_budget", return_value=1000),
        patch("app.services.wiki_engine.get_llm_provider", return_value=provider),
    ):
        result = await ingest_source(db_session, class_id, record.id, task_id=task_id)

    assert result.error == "Cancelled by user"
    assert await _pages(db_session, class_id) == {}


async def test_later_chunk_updates_page_it_was_shown(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    text = "\n".join(f"Line {i} about a long topic in the notes." for i in range(120))
    record = await _make_file(db_session, class_id, tmp_path, text)
    calls = 0

    async def summary_grows_each_chunk(*args: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _page_xml("pages/source-summaries/notes.md", "Notes", "Part one summary.")
        parts = ", ".join(f"part {n}" for n in range(2, calls + 1))
        return _page_xml(
            "pages/source-summaries/notes.md",
            "Notes",
            f"Part one summary, now with {parts} as well.",
            action="update",
        )

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=summary_grows_each_chunk)

    with (
        patch("app.services.wiki_engine._prompt_budget", return_value=1000),
        patch("app.services.wiki_engine.get_llm_provider", return_value=provider),
    ):
        result = await ingest_source(db_session, class_id, record.id)

    second_prompt = provider.complete.await_args_list[1].args[1]
    assert "Existing Pages You May Update" in second_prompt
    assert "Part one summary." in second_prompt
    assert result.pages_created == ["pages/source-summaries/notes.md"]
    page = (await _pages(db_session, class_id))["pages/source-summaries/notes.md"]
    assert f"part {calls} as well" in page.content


async def test_update_of_page_not_shown_is_skipped(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    old = "---\ntitle: Entropy\ntype: concept\n---\n\nFrom source A [a](hypatia://cite?file=a.pdf)."
    db_session.add(
        WikiPage(
            class_id=class_id,
            path="pages/concepts/entropy.md",
            title="Entropy",
            category=WikiCategory.CONCEPT,
            content=old,
            source_file_ids=["a"],
        )
    )
    record = await _make_file(db_session, class_id, tmp_path, "# Unrelated\n\nNothing shared.")
    provider = _provider(
        _page_xml("pages/concepts/entropy.md", "Entropy", "Only source B now.", action="update")
    )

    # The search that picks pages to show finds nothing, so entropy isn't shown.
    with (
        patch("app.services.wiki_engine.hybrid_search", AsyncMock(return_value=[])),
        patch("app.services.wiki_engine.get_llm_provider", return_value=provider),
    ):
        result = await ingest_source(db_session, class_id, record.id)

    assert result.success and result.pages_updated == []
    assert (await _pages(db_session, class_id))["pages/concepts/entropy.md"].content == old


async def test_update_that_drops_citations_keeps_old_page(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    old = (
        "---\ntitle: Entropy\ntype: concept\n---\n\nEntropy measures disorder "
        "[a](hypatia://cite?file=a.pdf&page=2)."
    )
    db_session.add(
        WikiPage(
            class_id=class_id,
            path="pages/concepts/entropy.md",
            title="Entropy",
            category=WikiCategory.CONCEPT,
            content=old,
            source_file_ids=["a"],
        )
    )
    await db_session.commit()
    record = await _make_file(db_session, class_id, tmp_path, "# Entropy\n\nMore on entropy.")
    search_hit = AsyncMock(
        return_value=[type("Hit", (), {"path": "pages/concepts/entropy.md", "title": "Entropy"})()]
    )
    provider = _provider(
        _page_xml(
            "pages/concepts/entropy.md",
            "Entropy",
            "Entropy measures disorder, rewritten from source B with no citation of A.",
            action="update",
        )
    )

    with (
        patch("app.services.wiki_engine.hybrid_search", search_hit),
        patch("app.services.wiki_engine.get_llm_provider", return_value=provider),
    ):
        result = await ingest_source(db_session, class_id, record.id)

    assert result.pages_updated == []
    assert (await _pages(db_session, class_id))["pages/concepts/entropy.md"].content == old


async def test_ingest_never_overwrites_user_edited_page(db_session: AsyncSession, tmp_path: Path):
    class_id = uuid.uuid4()
    db_session.add(
        WikiPage(
            class_id=class_id,
            path="pages/concepts/mine.md",
            title="Mine",
            category=WikiCategory.CONCEPT,
            content="My own notes.",
            user_edited=True,
        )
    )
    record = await _make_file(db_session, class_id, tmp_path)
    provider = _provider(_page_xml("pages/concepts/mine.md", "Mine", "LLM text."))

    with patch("app.services.wiki_engine.get_llm_provider", return_value=provider):
        result = await ingest_source(db_session, class_id, record.id)

    assert result.pages_created == [] and result.pages_updated == []
    assert (await _pages(db_session, class_id))["pages/concepts/mine.md"].content == "My own notes."


# ---------------------------------------------------------------------------
# Lock, mirror, revert, remove
# ---------------------------------------------------------------------------


async def test_operations_on_a_class_wait_for_its_lock(db_session: AsyncSession):
    class_id = uuid.uuid4()
    lock = class_operation_lock(class_id)
    await lock.acquire()
    try:
        summarize = asyncio.create_task(handle_summarize(db_session, class_id, "anything"))
        await asyncio.sleep(0.05)
        assert not summarize.done()
    finally:
        lock.release()
    result = await asyncio.wait_for(summarize, timeout=5)
    assert result.success is False  # no pages to summarize; it ran once unlocked


async def test_mirror_removes_files_without_a_row(db_session: AsyncSession):
    class_id = uuid.uuid4()
    stray = wiki_git.init_wiki_repo(str(class_id)) / "pages" / "old" / "gone.md"
    stray.parent.mkdir(parents=True)
    stray.write_text("left over", encoding="utf-8")
    db_session.add(
        WikiPage(
            class_id=class_id,
            path="pages/concepts/kept.md",
            title="Kept",
            category=WikiCategory.CONCEPT,
            content="Kept.",
        )
    )
    await db_session.commit()

    await mirror_to_disk(db_session, class_id, "test mirror")

    assert _page_files(class_id) == {"pages/concepts/kept.md"}
    assert not stray.parent.exists()
    index = (wiki_git.wiki_dir(str(class_id)) / "index.md").read_text(encoding="utf-8")
    assert "[Kept](pages/concepts/kept.md)" in index


@pytest.mark.skipif(not wiki_git._GIT_AVAILABLE, reason="git is not installed")
async def test_revert_loads_old_pages_into_the_database(db_session: AsyncSession):
    class_id = uuid.uuid4()
    path = "pages/concepts/x.md"
    v1 = '---\ntitle: "X"\ntype: concept\nsources: []\ntags: []\n---\n\nVersion one.'
    await update_wiki_page(db_session, class_id, path, v1)
    first_sha = wiki_git.get_wiki_history(str(class_id))[0]["sha"]
    await update_wiki_page(db_session, class_id, path, v1.replace("one", "two"), is_user_edit=True)
    await update_wiki_page(db_session, class_id, "pages/concepts/new.md", v1)

    assert await revert_wiki(db_session, class_id, first_sha) is True

    pages = await _pages(db_session, class_id)
    assert set(pages) == {path}
    assert "Version one." in pages[path].content
    assert pages[path].user_edited is False
    assert _page_files(class_id) == {path}
    assert [r.path for r in await hybrid_search(db_session, class_id, "version")] == [path]


async def test_remove_keeps_user_edited_page_and_deletes_files_after_commit(
    db_session: AsyncSession, tmp_path: Path
):
    class_id = uuid.uuid4()
    record = await _make_file(db_session, class_id, tmp_path)
    raw = Path(record.raw_path)
    raw.write_bytes(b"pdf")
    source = str(record.id)
    db_session.add_all(
        [
            WikiPage(
                class_id=class_id,
                path="pages/concepts/generated.md",
                title="Generated",
                category=WikiCategory.CONCEPT,
                content="Generated.",
                source_file_ids=[source],
            ),
            WikiPage(
                class_id=class_id,
                path="pages/concepts/mine.md",
                title="Mine",
                category=WikiCategory.CONCEPT,
                content="My notes, see [[generated]].",
                source_file_ids=[source],
                user_edited=True,
            ),
        ]
    )
    await db_session.commit()

    result = await handle_remove(db_session, class_id, record.original_filename)

    assert result.pages_deleted == ["pages/concepts/generated.md"]
    assert result.pages_updated == ["pages/concepts/mine.md"]
    pages = await _pages(db_session, class_id)
    assert set(pages) == {"pages/concepts/mine.md"}
    assert pages["pages/concepts/mine.md"].source_file_ids == []
    assert pages["pages/concepts/mine.md"].content == "My notes, see generated."
    assert not raw.exists()
    assert not Path(record.converted_path or "").exists()
