"""Semantic search via sentence-transformers embeddings.

The sentence-transformers library is an optional dependency. If not installed,
all public functions raise ImportError with a clear message. The hybrid search
layer (wiki_search.py) catches this and falls back to FTS5-only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.logging import get_logger

logger = get_logger()

_model = None
_EMBEDDING_DIM = 384
_MODEL_NAME = "all-MiniLM-L6-v2"


def _normalize_uuid(value: uuid.UUID | str) -> str:
    """Normalize a UUID to 32-char lowercase hex (no hyphens) to match SQLAlchemy Uuid storage."""
    return str(value).replace("-", "").lower()


def _get_model():
    """Lazy-load the SentenceTransformer model on first use."""
    global _model
    if _model is not None:
        return _model

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "sentence-transformers is not installed. "
            "Install with: pip install 'hypatia-backend[semantic]'"
        )

    logger.info("loading_embedding_model", model=_MODEL_NAME)
    _model = SentenceTransformer(_MODEL_NAME)
    logger.info("embedding_model_loaded", model=_MODEL_NAME)
    return _model


@dataclass
class SemanticSearchResult:
    """A result from semantic similarity search."""

    page_id: str
    class_id: str
    path: str
    title: str
    score: float
    category: str = ""


def generate_embedding(text_content: str) -> bytes:
    """Encode text into a float32 byte blob (384 dimensions = 1536 bytes)."""
    model = _get_model()
    embedding = model.encode(text_content, convert_to_numpy=True, normalize_embeddings=True)
    return embedding.astype(np.float32).tobytes()


async def upsert_embedding(session: AsyncSession, page_id: uuid.UUID | str, content: str) -> None:
    """Generate and store (or replace) the embedding for a wiki page."""
    pid = _normalize_uuid(page_id)
    embedding_bytes = generate_embedding(content)

    await session.execute(
        text("DELETE FROM wiki_page_embeddings WHERE CAST(page_id AS TEXT) = :pid"),
        {"pid": pid},
    )
    new_id = str(uuid.uuid4()).replace("-", "")
    await session.execute(
        text("""
            INSERT INTO wiki_page_embeddings (id, page_id, embedding)
            VALUES (:id, :page_id, :embedding)
        """),
        {"id": new_id, "page_id": pid, "embedding": embedding_bytes},
    )


async def delete_embedding(session: AsyncSession, page_id: uuid.UUID | str) -> None:
    """Remove the embedding for a wiki page."""
    await session.execute(
        text("DELETE FROM wiki_page_embeddings WHERE CAST(page_id AS TEXT) = :pid"),
        {"pid": _normalize_uuid(page_id)},
    )


async def search_semantic(
    session: AsyncSession,
    class_id: uuid.UUID | str,
    query: str,
    limit: int = 10,
) -> list[SemanticSearchResult]:
    """Find pages by cosine similarity to the query embedding.

    Loads all embeddings for the class into memory and computes similarities
    in numpy. For typical wiki sizes (<10K pages) this is fast (~ms).
    """
    query_embedding = np.frombuffer(generate_embedding(query), dtype=np.float32)

    cid = _normalize_uuid(class_id)
    result = await session.execute(
        text("""
            SELECT e.page_id, e.embedding, w.class_id, w.path, w.title, w.category
            FROM wiki_page_embeddings e
            JOIN wiki_pages w ON CAST(w.id AS TEXT) = CAST(e.page_id AS TEXT)
            WHERE CAST(w.class_id AS TEXT) = :cid
        """),
        {"cid": cid},
    )
    rows = result.fetchall()

    if not rows:
        return []

    scores = []
    for row in rows:
        page_emb = np.frombuffer(row.embedding, dtype=np.float32)
        score = float(np.dot(query_embedding, page_emb))
        scores.append((row, score))

    scores.sort(key=lambda x: x[1], reverse=True)

    return [
        SemanticSearchResult(
            page_id=str(row.page_id),
            class_id=str(row.class_id),
            path=row.path,
            title=row.title,
            score=score,
            category=row.category or "",
        )
        for row, score in scores[:limit]
    ]
