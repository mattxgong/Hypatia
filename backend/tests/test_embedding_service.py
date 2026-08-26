"""Tests for the embedding service (Phase 7, Task 7.2)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.embedding_service import (
    _EMBEDDING_DIM,
    delete_embedding,
    generate_embedding,
    search_semantic,
    upsert_embedding,
)


@pytest.fixture
async def emb_session() -> AsyncIterator[AsyncSession]:
    """Session with wiki_pages and wiki_page_embeddings tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(
            text("""
                CREATE TABLE wiki_pages (
                    id TEXT PRIMARY KEY,
                    class_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT ''
                )
            """)
        )
        await conn.execute(
            text("""
                CREATE TABLE wiki_page_embeddings (
                    id TEXT PRIMARY KEY,
                    page_id TEXT NOT NULL UNIQUE,
                    embedding BLOB NOT NULL,
                    FOREIGN KEY (page_id) REFERENCES wiki_pages(id)
                )
            """)
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _mock_encode(texts, **kwargs):
    """Return deterministic normalized embeddings based on text hash."""
    if isinstance(texts, str):
        texts = [texts]
    results = []
    for t in texts:
        rng = np.random.default_rng(hash(t) % (2**31))
        vec = rng.standard_normal(_EMBEDDING_DIM).astype(np.float32)
        vec /= np.linalg.norm(vec)
        results.append(vec)
    if len(results) == 1:
        return results[0]
    return np.array(results)


@pytest.fixture(autouse=True)
def mock_sentence_transformer():
    """Mock the SentenceTransformer model for all tests."""
    import app.services.embedding_service as emb_mod

    mock_model = MagicMock()
    mock_model.encode = _mock_encode
    emb_mod._model = mock_model
    yield
    emb_mod._model = None


async def test_generate_embedding_shape():
    result = generate_embedding("hello world")
    assert isinstance(result, bytes)
    assert len(result) == _EMBEDDING_DIM * 4  # float32 = 4 bytes each


async def test_upsert_and_delete(emb_session: AsyncSession):
    class_id = uuid.uuid4()
    page_id = uuid.uuid4()

    await emb_session.execute(
        text("""
            INSERT INTO wiki_pages (id, class_id, path, title, category, content)
            VALUES (:id, :cid, :path, :title, :cat, :content)
        """),
        {
            "id": page_id.hex,
            "cid": class_id.hex,
            "path": "test.md",
            "title": "Test",
            "cat": "concept",
            "content": "test",
        },
    )
    await emb_session.commit()

    await upsert_embedding(emb_session, page_id, "Some content about testing")
    await emb_session.commit()

    row = await emb_session.execute(
        text("SELECT COUNT(*) as cnt FROM wiki_page_embeddings WHERE page_id = :pid"),
        {"pid": str(page_id).replace("-", "")},
    )
    assert row.fetchone().cnt == 1

    await upsert_embedding(emb_session, page_id, "Updated content")
    await emb_session.commit()

    row = await emb_session.execute(
        text("SELECT COUNT(*) as cnt FROM wiki_page_embeddings WHERE page_id = :pid"),
        {"pid": str(page_id).replace("-", "")},
    )
    assert row.fetchone().cnt == 1

    await delete_embedding(emb_session, page_id)
    await emb_session.commit()

    row = await emb_session.execute(
        text("SELECT COUNT(*) as cnt FROM wiki_page_embeddings WHERE page_id = :pid"),
        {"pid": str(page_id).replace("-", "")},
    )
    assert row.fetchone().cnt == 0


async def test_search_semantic(emb_session: AsyncSession):
    class_id = uuid.uuid4()

    pages = [
        (uuid.uuid4(), "ml.md", "Machine Learning", "concept", "Machine learning algorithms"),
        (uuid.uuid4(), "bio.md", "Biology", "concept", "Cell biology and genetics"),
        (uuid.uuid4(), "nn.md", "Neural Networks", "concept", "Deep learning neural networks"),
    ]

    for pid, path, title, cat, content in pages:
        await emb_session.execute(
            text("""
                INSERT INTO wiki_pages (id, class_id, path, title, category, content)
                VALUES (:id, :cid, :path, :title, :cat, :content)
            """),
            {
                "id": pid.hex,
                "cid": class_id.hex,
                "path": path,
                "title": title,
                "cat": cat,
                "content": content,
            },
        )
        await upsert_embedding(emb_session, pid, content)
    await emb_session.commit()

    results = await search_semantic(emb_session, class_id, "machine learning algorithms", limit=2)
    assert len(results) == 2
    assert all(r.class_id.replace("-", "") == class_id.hex for r in results)
    assert results[0].score >= results[1].score


async def test_search_semantic_empty_class(emb_session: AsyncSession):
    results = await search_semantic(emb_session, uuid.uuid4(), "anything")
    assert results == []


def test_import_error_when_no_sentence_transformers():
    """Verify clear error when sentence-transformers is absent."""
    import app.services.embedding_service as emb_mod

    emb_mod._model = None

    with (
        patch.dict("sys.modules", {"sentence_transformers": None}),
        patch(
            "builtins.__import__",
            side_effect=ImportError("No module named 'sentence_transformers'"),
        ),
        pytest.raises(ImportError, match="sentence-transformers is not installed"),
    ):
        emb_mod._get_model()
