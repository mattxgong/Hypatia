"""Performance benchmark tests (Task 8.4).

These benchmarks measure key backend operations to establish baseline
performance and catch regressions. Run with:

    pytest tests/benchmarks/ -v
"""

from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.db_models import Base, Class, WikiPage
from app.services.task_manager import TaskManager
from app.services.wiki_search import ensure_fts_index

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def bench_engine():
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
async def bench_session(bench_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bench_engine, expire_on_commit=False)


class TestDatabaseBenchmarks:
    """Measure core database operation latency."""

    async def test_class_create_latency(self, bench_session) -> None:
        async with bench_session() as session:
            start = time.perf_counter()
            for i in range(100):
                session.add(Class(name=f"Bench Class {i}", description="benchmark"))
            await session.commit()
            elapsed = time.perf_counter() - start

        assert elapsed < 5.0, f"Creating 100 classes took {elapsed:.2f}s (expected <5s)"

    async def test_wiki_page_insert_latency(self, bench_session) -> None:
        async with bench_session() as session:
            cls = Class(name="Bench", description="bench")
            session.add(cls)
            await session.commit()
            await session.refresh(cls)

            start = time.perf_counter()
            for i in range(200):
                session.add(
                    WikiPage(
                        class_id=cls.id,
                        path=f"pages/page-{i}.md",
                        title=f"Page {i}",
                        category="topic",
                        content=f"Content for page {i}. " * 50,
                    )
                )
            await session.commit()
            elapsed = time.perf_counter() - start

        assert elapsed < 10.0, f"Inserting 200 wiki pages took {elapsed:.2f}s (expected <10s)"

    async def test_wiki_page_query_latency(self, bench_session) -> None:
        async with bench_session() as session:
            cls = Class(name="Query Bench", description="bench")
            session.add(cls)
            await session.commit()
            await session.refresh(cls)

            for i in range(100):
                session.add(
                    WikiPage(
                        class_id=cls.id,
                        path=f"pages/q-{i}.md",
                        title=f"Query Page {i}",
                        category="topic",
                        content=f"Query content {i}",
                    )
                )
            await session.commit()

            start = time.perf_counter()
            for _ in range(50):
                result = await session.execute(select(WikiPage).where(WikiPage.class_id == cls.id))
                result.scalars().all()
            elapsed = time.perf_counter() - start

        assert elapsed < 5.0, f"50 wiki page queries took {elapsed:.2f}s (expected <5s)"


class TestTaskManagerBenchmarks:
    """Measure task manager throughput."""

    async def test_task_lifecycle_throughput(self) -> None:
        tm = TaskManager()
        start = time.perf_counter()

        task_ids = []
        for i in range(500):
            tid = tm.start_task("benchmark", f"class-{i % 10}")
            task_ids.append(tid)

        for tid in task_ids:
            tm.update_progress(tid, 50, "halfway")

        for tid in task_ids[:250]:
            tm.complete_task(tid)
        for tid in task_ids[250:]:
            tm.fail_task(tid, "bench error")

        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"500 task lifecycles took {elapsed:.2f}s (expected <2s)"

    async def test_list_tasks_with_cleanup(self) -> None:
        tm = TaskManager()
        for i in range(100):
            tid = tm.start_task("bench", "class-1")
            tm.complete_task(tid)

        start = time.perf_counter()
        for _ in range(100):
            tm.list_tasks()
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"100 list_tasks calls took {elapsed:.2f}s (expected <1s)"


class TestAPIBenchmarks:
    """Measure API endpoint response times using the test client."""

    async def test_health_check_latency(self) -> None:
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/health")

            start = time.perf_counter()
            for _ in range(100):
                resp = await client.get("/health")
                assert resp.status_code == 200
            elapsed = time.perf_counter() - start

        assert elapsed < 5.0, f"100 health checks took {elapsed:.2f}s (expected <5s)"
