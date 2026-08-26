"""FTS5 full-text search for wiki pages.

Provides keyword search with BM25 ranking, semantic search via embeddings,
and hybrid fusion (Reciprocal Rank Fusion). Used by the wiki engine for
context retrieval and by the search API endpoint.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.utils.logging import get_logger

logger = get_logger()

SearchMode = Literal["keyword", "semantic", "hybrid"]


@dataclass
class WikiSearchResult:
    """A search result from the FTS5 index."""

    page_id: str
    class_id: str
    path: str
    title: str
    rank: float
    snippet: str = ""
    category: str = ""


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


def _normalize_uuid(value: uuid.UUID | str) -> str:
    """Normalize a UUID to 32-char lowercase hex (no hyphens) to match SQLAlchemy Uuid storage."""
    return str(value).replace("-", "").lower()


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
    pid = _normalize_uuid(page_id)
    cid = _normalize_uuid(class_id)
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
        {"pid": _normalize_uuid(page_id)},
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
    category: str | None = None,
    offset: int = 0,
) -> list[WikiSearchResult]:
    """Search wiki pages by keyword using BM25 ranking.

    Returns results for the specified Class only, ordered by relevance.
    Supports optional category filtering and offset-based pagination.
    """
    if not query.strip():
        return []

    sanitized = _sanitize_fts_query(query)
    if not sanitized:
        return []

    cid = _normalize_uuid(class_id)
    params: dict = {"query": sanitized, "cid": cid, "limit": limit, "offset": offset}

    category_clause = ""
    if category:
        category_clause = "AND w.category = :category"
        params["category"] = category

    result = await session.execute(
        text(f"""
            SELECT f.page_id, f.class_id, f.path, f.title, f.rank,
                   snippet(wiki_pages_fts, 4, '<b>', '</b>', '...', 32) as snippet,
                   w.category
            FROM wiki_pages_fts f
            JOIN wiki_pages w ON CAST(w.id AS TEXT) = f.page_id
            WHERE wiki_pages_fts MATCH :query AND f.class_id = :cid
            {category_clause}
            ORDER BY f.rank
            LIMIT :limit OFFSET :offset
        """),
        params,
    )

    return [
        WikiSearchResult(
            page_id=row.page_id,
            class_id=row.class_id,
            path=row.path,
            title=row.title,
            rank=row.rank,
            snippet=row.snippet or "",
            category=row.category or "",
        )
        for row in result.fetchall()
    ]


async def count_wiki_search_results(
    session: AsyncSession,
    class_id: uuid.UUID | str,
    query: str,
    category: str | None = None,
) -> int:
    """Count total matching results (for pagination metadata)."""
    if not query.strip():
        return 0

    sanitized = _sanitize_fts_query(query)
    if not sanitized:
        return 0

    cid = _normalize_uuid(class_id)
    params: dict = {"query": sanitized, "cid": cid}

    category_clause = ""
    if category:
        category_clause = "AND w.category = :category"
        params["category"] = category

    result = await session.execute(
        text(f"""
            SELECT COUNT(*) as cnt
            FROM wiki_pages_fts f
            JOIN wiki_pages w ON CAST(w.id AS TEXT) = f.page_id
            WHERE wiki_pages_fts MATCH :query AND f.class_id = :cid
            {category_clause}
        """),
        params,
    )

    row = result.fetchone()
    return row.cnt if row else 0


# ---------------------------------------------------------------------------
# Hybrid search: BM25 + semantic fusion via Reciprocal Rank Fusion (RRF)
# ---------------------------------------------------------------------------

_RRF_K = 60  # Literature default for RRF smoothing parameter


async def hybrid_search(
    session: AsyncSession,
    class_id: uuid.UUID | str,
    query: str,
    limit: int = 20,
    category: str | None = None,
    offset: int = 0,
    mode: SearchMode = "hybrid",
) -> list[WikiSearchResult]:
    """Search wiki pages using keyword, semantic, or hybrid (RRF) fusion.

    Modes:
      - "keyword": FTS5 only (BM25 ranking).
      - "semantic": Embedding similarity only.
      - "hybrid" (default): Both methods fused via Reciprocal Rank Fusion.

    Falls back to keyword-only if embedding service is unavailable.
    """
    if not query.strip():
        return []

    if mode == "keyword":
        return await search_wiki_pages(
            session, class_id, query, limit=limit, category=category, offset=offset
        )

    if mode == "semantic":
        return await _semantic_as_wiki_results(
            session, class_id, query, limit=limit, category=category, offset=offset
        )

    # Hybrid mode: run both and fuse
    keyword_results = await search_wiki_pages(
        session, class_id, query, limit=limit + offset, category=category, offset=0
    )

    semantic_results = await _get_semantic_results(session, class_id, query, limit=limit + offset)

    if not semantic_results:
        # Fallback: no embeddings available, just use keyword results
        return keyword_results[offset : offset + limit]

    # Reciprocal Rank Fusion
    scores: dict[str, float] = {}
    metadata: dict[str, WikiSearchResult] = {}

    for rank_idx, r in enumerate(keyword_results):
        scores[r.page_id] = scores.get(r.page_id, 0) + 1.0 / (_RRF_K + rank_idx + 1)
        metadata[r.page_id] = r

    for rank_idx, r in enumerate(semantic_results):
        scores[r.page_id] = scores.get(r.page_id, 0) + 1.0 / (_RRF_K + rank_idx + 1)
        if r.page_id not in metadata:
            metadata[r.page_id] = r

    # Sort by fused score descending
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # Apply category filter on fused results (semantic results may not have been filtered)
    results: list[WikiSearchResult] = []
    for page_id, fused_score in ranked:
        entry = metadata[page_id]
        if category and entry.category != category:
            continue
        results.append(
            WikiSearchResult(
                page_id=entry.page_id,
                class_id=entry.class_id,
                path=entry.path,
                title=entry.title,
                rank=fused_score,
                snippet=entry.snippet,
                category=entry.category,
            )
        )

    return results[offset : offset + limit]


async def _get_semantic_results(
    session: AsyncSession,
    class_id: uuid.UUID | str,
    query: str,
    limit: int = 20,
) -> list[WikiSearchResult]:
    """Get semantic search results, returning empty list on any failure."""
    try:
        from app.services.embedding_service import search_semantic

        semantic_raw = await search_semantic(session, class_id, query, limit=limit)
        return [
            WikiSearchResult(
                page_id=r.page_id,
                class_id=r.class_id,
                path=r.path,
                title=r.title,
                rank=r.score,
                snippet="",
                category=r.category,
            )
            for r in semantic_raw
        ]
    except ImportError:
        logger.debug("semantic_search_unavailable", reason="sentence-transformers not installed")
        return []
    except Exception:
        logger.warning("semantic_search_error", exc_info=True)
        return []


async def _semantic_as_wiki_results(
    session: AsyncSession,
    class_id: uuid.UUID | str,
    query: str,
    limit: int = 20,
    category: str | None = None,
    offset: int = 0,
) -> list[WikiSearchResult]:
    """Run semantic-only search, applying category filter and pagination."""
    results = await _get_semantic_results(session, class_id, query, limit=limit + offset + 50)
    if category:
        results = [r for r in results if r.category == category]
    return results[offset : offset + limit]
