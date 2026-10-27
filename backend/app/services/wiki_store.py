"""The database is the source of truth for wiki pages; disk is a mirror of it.

Every page lives in ``wiki_pages``. After an operation commits, it calls
:func:`mirror_to_disk`, which rewrites ``wiki/pages/**`` and ``index.md`` from
the database, deletes page files that no longer have a row, and commits the
result to the Class's git repo for history and export. Nothing reads page
files back, so a failed or cancelled operation, which never commits, leaves
both the database and disk as they were.

``log.md`` is the one wiki file that isn't derived from the database: it is
an append-only record written after each operation.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import WikiPage
from app.services.wiki_git import commit_wiki_change, init_wiki_repo, wiki_dir
from app.utils.logging import get_logger

logger = get_logger()

_CATEGORY_LABELS = {
    "source-summary": "Source Summaries",
    "concept": "Concepts",
    "entity": "Entities",
    "synthesis": "Synthesis",
}

_operation_locks: dict[uuid.UUID, asyncio.Lock] = {}
_mirror_locks: dict[uuid.UUID, asyncio.Lock] = {}


def class_operation_lock(class_id: uuid.UUID) -> asyncio.Lock:
    """Serializes the long wiki operations of one Class: ingest, /rebuild,
    /remove and /summarize. Without it an upload could be ingested into the
    wiki while a rebuild is tearing it down and regenerating it.

    Callers take it at the top level only: /rebuild holds it while it calls
    ``ingest_source``, which must therefore not take it again.
    """
    return _operation_locks.setdefault(class_id, asyncio.Lock())


def build_index(pages: list[WikiPage]) -> str:
    """The wiki index, grouped by category, with each page's source count."""
    sections: dict[str, list[str]] = {category: [] for category in _CATEGORY_LABELS}
    for page in sorted(pages, key=lambda p: p.path):
        if not page.path.startswith("pages/"):
            continue
        category: str = page.category.value if page.category.value in sections else "concept"
        count = len(page.source_file_ids or [])
        suffix = f" ({count} source{'s' if count != 1 else ''})" if count else ""
        sections[category].append(f"- [{page.title}]({page.path}){suffix}")

    lines = ["# Wiki Index\n"]
    for category, label in _CATEGORY_LABELS.items():
        if sections[category]:
            lines.append(f"\n## {label}\n")
            lines.extend(sections[category])
    return "\n".join(lines) + "\n"


async def load_pages(session: AsyncSession, class_id: uuid.UUID) -> list[WikiPage]:
    result = await session.execute(select(WikiPage).where(WikiPage.class_id == class_id))
    return list(result.scalars().all())


async def load_index(session: AsyncSession, class_id: uuid.UUID) -> str:
    return build_index(await load_pages(session, class_id))


async def mirror_to_disk(session: AsyncSession, class_id: uuid.UUID, message: str) -> None:
    """Rewrite the Class's wiki files from the database and commit them to git.

    Call only after the session has committed. Failures are logged, not
    raised: the database already holds the result, and the next mirror
    rewrites everything anyway.
    """
    pages = await load_pages(session, class_id)
    files = {p.path: p.content for p in pages if p.path.startswith("pages/")}
    index = build_index(pages)
    lock = _mirror_locks.setdefault(class_id, asyncio.Lock())
    async with lock:
        try:
            await asyncio.to_thread(_write_mirror, str(class_id), files, index, message)
        except Exception:
            logger.exception("wiki_mirror_failed", class_id=str(class_id))


def _write_mirror(class_id: str, files: dict[str, str], index: str, message: str) -> None:
    root = init_wiki_repo(class_id)
    pages_dir = root / "pages"
    for rel_path, content in files.items():
        target = root / rel_path
        if target.exists() and target.read_text(encoding="utf-8") == content:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    if pages_dir.exists():
        for existing in pages_dir.rglob("*"):
            if existing.is_file() and existing.relative_to(root).as_posix() not in files:
                existing.unlink()
        # Remove directories emptied above, deepest first.
        for directory in sorted(pages_dir.rglob("*"), key=lambda d: len(d.parts), reverse=True):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()

    (root / "index.md").write_text(index, encoding="utf-8")
    commit_wiki_change(class_id, message)


def append_log(class_id: uuid.UUID | str, action: str, detail: str, extra: str = "") -> None:
    """Append a timestamped entry to the Class's ``log.md``."""
    log_file: Path = wiki_dir(str(class_id)) / "log.md"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    entry = f"\n## [{timestamp}] {action} | {detail}\n{extra}"
    is_new = not log_file.exists()
    with log_file.open("a", encoding="utf-8") as f:
        if is_new:
            f.write("# Wiki Log\n")
        f.write(entry)
