"""Task 1.5 acceptance: Alembic migrations create all tables from scratch."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

from alembic import command
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


def test_unique_file_name_migration_renames_legacy_duplicates(isolated_data_dir: Path) -> None:
    config = database._alembic_config()
    isolated_data_dir.mkdir(parents=True)
    command.upgrade(config, "d8f3a72c1e95")

    db_path = isolated_data_dir / "hypatia.db"
    class_id = uuid.uuid4().hex
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO classes (id, name, created_at, updated_at) "
                    "VALUES (:id, 'Legacy', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
                ),
                {"id": class_id},
            )
            for index, name in enumerate(["notes.md", "notes.md", "notes-1.md", "notes.md"]):
                conn.execute(
                    sa.text(
                        "INSERT INTO files (id, class_id, original_filename, file_type, "
                        "file_size_bytes, raw_path, status, created_at, updated_at) VALUES "
                        "(:id, :class_id, :name, 'markdown', 1, :raw, 'ready', :created, :created)"
                    ),
                    {
                        "id": uuid.uuid4().hex,
                        "class_id": class_id,
                        "name": name,
                        "raw": f"raw/{index}.md",
                        "created": f"2026-01-0{index + 1} 00:00:00",
                    },
                )

        command.upgrade(config, "head")

        with engine.connect() as conn:
            names = conn.execute(
                sa.text("SELECT original_filename FROM files ORDER BY created_at")
            ).scalars()
            assert list(names) == ["notes.md", "notes-2.md", "notes-1.md", "notes-3.md"]
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(
                    sa.text(
                        "INSERT INTO files (id, class_id, original_filename, file_type, "
                        "file_size_bytes, raw_path, status, created_at, updated_at) VALUES "
                        "(:id, :class_id, 'notes.md', 'markdown', 1, 'raw/x.md', 'ready', "
                        "'2026-02-01 00:00:00', '2026-02-01 00:00:00')"
                    ),
                    {"id": uuid.uuid4().hex, "class_id": class_id},
                )
    finally:
        engine.dispose()
