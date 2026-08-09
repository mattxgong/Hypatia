"""Task 1.5 acceptance: Alembic migrations create all tables from scratch."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

from app import database
from app.config import settings


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)
    return data_dir


async def test_run_migrations_creates_all_tables(isolated_data_dir: Path) -> None:
    await database.run_migrations()

    db_path = isolated_data_dir / "hypatia.db"
    assert db_path.is_file()

    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        inspector = sa.inspect(engine)
        table_names = set(inspector.get_table_names())
    finally:
        engine.dispose()

    assert {"classes", "files", "wiki_pages", "chat_messages"}.issubset(table_names)


async def test_run_migrations_is_idempotent(isolated_data_dir: Path) -> None:
    await database.run_migrations()
    await database.run_migrations()

    db_path = isolated_data_dir / "hypatia.db"
    assert db_path.is_file()
