"""E2E test fixtures (Task 8.2).

Shared conftest for full-stack E2E tests that exercise the real FastAPI app
with a temporary data directory and in-memory SQLite database.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import get_session
from app.dependencies import check_llm_available
from app.main import app
from app.models.db_models import Base
from app.services.llm_providers.base import LLMProvider
from app.services.wiki_search import ensure_fts_index


class MockLLMProvider(LLMProvider):
    """Deterministic mock LLM provider for structural E2E tests."""

    def __init__(self) -> None:
        self.call_log: list[dict[str, str]] = []

    async def complete(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> str:
        self.call_log.append({"system": system_prompt, "user": user_prompt})

        if "index" in user_prompt.lower() or "wiki index" in system_prompt.lower():
            return (
                "# Wiki Index\n\nWelcome to the knowledge base.\n\n## Pages\n\n- [[Test Topic]]\n"
            )

        if "summarize" in user_prompt.lower() or "summary" in system_prompt.lower():
            return (
                "# Summary\n\n"
                "This is a mock summary of the uploaded sources.\n\n"
                "## Key Points\n\n"
                "- Point 1 from the material\n"
                "- Point 2 from the material\n"
            )

        if "lint" in user_prompt.lower() or "contradiction" in system_prompt.lower():
            return "No contradictions found in the current wiki."

        return (
            "# Test Topic\n\n"
            "This is a mock LLM response about the uploaded material.\n\n"
            "## Details\n\n"
            "The source material covers important concepts.\n"
            "[Source: note.md]\n"
        )

    async def stream(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> AsyncIterator[str]:
        full_response = await self.complete(system_prompt, user_prompt, max_tokens=max_tokens)
        for word in full_response.split():
            yield word + " "

    async def list_models(self) -> list[str]:
        return ["mock-model"]


@pytest.fixture
def mock_llm() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture
async def e2e_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_fts_index(engine)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def e2e_session_factory(e2e_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(e2e_engine, expire_on_commit=False)


@pytest.fixture
async def e2e_client(
    e2e_session_factory: async_sessionmaker[AsyncSession],
    mock_llm: MockLLMProvider,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> AsyncIterator[AsyncClient]:
    """Full-stack test client with temporary data dir and mock LLM."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(settings, "data_dir", data_dir)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with e2e_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[check_llm_available] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch("app.services.llm_service.get_llm_provider", return_value=mock_llm):
            yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def e2e_class(e2e_client: AsyncClient) -> dict:
    """Create a class and return its JSON representation."""
    name = f"E2E Test Class {uuid.uuid4().hex[:8]}"
    resp = await e2e_client.post(
        "/api/classes",
        json={"name": name, "description": "Created for E2E testing"},
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def sample_source_file(tmp_path: Path) -> Path:
    """Create a minimal text file pretending to be a markdown source."""
    f = tmp_path / "test_notes.md"
    f.write_text(
        "# Lecture Notes\n\n"
        "## Introduction\n\n"
        "This lecture covers the fundamentals of machine learning.\n\n"
        "## Key Concepts\n\n"
        "- Supervised learning uses labeled data\n"
        "- Unsupervised learning finds patterns in unlabeled data\n"
        "- Reinforcement learning optimizes actions via rewards\n"
    )
    return f


@pytest.fixture
def sample_files(tmp_path: Path) -> dict[str, Path]:
    """Create multiple sample files of different types."""
    md_file = tmp_path / "notes.md"
    md_file.write_text("# Notes\n\nImportant concepts about physics.\n")

    md_file2 = tmp_path / "lecture.md"
    md_file2.write_text("# Lecture\n\nAdvanced topics in mathematics.\n")

    md_file3 = tmp_path / "summary.md"
    md_file3.write_text("# Summary\n\nOverview of chemistry topics.\n")

    return {"notes": md_file, "lecture": md_file2, "summary": md_file3}
