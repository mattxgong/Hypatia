"""FTS5 full-text search for wiki pages.

Provides a minimal search layer used by the wiki engine for finding relevant
context pages during ingestion and /ask queries. The full search UI and
advanced features are deferred to Phase 7.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.utils.logging import get_logger

logger = get_logger()


@dataclass
class WikiSearchResult:
    """A search result from the FTS5 index."""

    page_id: str
    class_id: str
    path: str
    title: str
    rank: float
    snippet: str = ""


async def ensure_fts_index(engine: AsyncEngine) -> None:
    """Create the FTS5 virtual table if it does not already exist.

    Called during app startup as a safety net: the Alembic migration is the
    canonical creation path, but this handles cases where the DB exists without
    migrations having run (e.g. tests, fresh dev setups).
    """
    async with engine.begin() as conn:
        await conn.execute(
            text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS wiki_pages_fts USING fts5(
                page_id UNINDEXED,
                class_id UNINDEXED,
                path UNINDEXED,
                title,
                content,
                tags
            )
        """)
        )
    logger.info("fts_index_ensured")


async def sync_fts_page(
    session: AsyncSession,
    page_id: uuid.UUID | str,
    class_id: uuid.UUID | str,
    path: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
) -> None:
    """Insert or replace a page's entry in the FTS5 index."""
    pid = str(page_id)
    cid = str(class_id)
    tags_str = " ".join(tags) if tags else ""

    await session.execute(
        text("DELETE FROM wiki_pages_fts WHERE page_id = :pid"),
        {"pid": pid},
    )
    await session.execute(
        text("""
            INSERT INTO wiki_pages_fts (page_id, class_id, path, title, content, tags)
            VALUES (:pid, :cid, :path, :title, :content, :tags)
        """),
        {
            "pid": pid,
            "cid": cid,
            "path": path,
            "title": title,
            "content": content,
            "tags": tags_str,
        },
    )


async def delete_fts_page(session: AsyncSession, page_id: uuid.UUID | str) -> None:
    """Remove a page from the FTS5 index."""
    await session.execute(
        text("DELETE FROM wiki_pages_fts WHERE page_id = :pid"),
        {"pid": str(page_id)},
    )


def _sanitize_fts_query(query: str) -> str:
    """Sanitize a user query for FTS5 MATCH syntax.

    Wraps each word in double quotes to prevent FTS5 from interpreting
    special characters (?, *, ^, etc.) as operators.
    """
    import re

    words = re.findall(r"\w+", query)
    if not words:
        return ""
    return " OR ".join(f'"{w}"' for w in words)


async def search_wiki_pages(
    session: AsyncSession,
    class_id: uuid.UUID | str,
    query: str,
    limit: int = 10,
) -> list[WikiSearchResult]:
    """Search wiki pages by keyword using BM25 ranking.

    Returns results for the specified Class only, ordered by relevance.
    """
    if not query.strip():
        return []

    sanitized = _sanitize_fts_query(query)
    if not sanitized:
        return []

    cid = str(class_id)
    result = await session.execute(
        text("""
            SELECT page_id, class_id, path, title, rank,
                   snippet(wiki_pages_fts, 4, '<b>', '</b>', '...', 32) as snippet
            FROM wiki_pages_fts
            WHERE wiki_pages_fts MATCH :query AND class_id = :cid
            ORDER BY rank
            LIMIT :limit
        """),
        {"query": sanitized, "cid": cid, "limit": limit},
    )

    return [
        WikiSearchResult(
            page_id=row.page_id,
            class_id=row.class_id,
            path=row.path,
            title=row.title,
            rank=row.rank,
            snippet=row.snippet or "",
        )
        for row in result.fetchall()
    ]
