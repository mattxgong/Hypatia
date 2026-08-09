"""Database engine, session factory, and migration runner (Task 1.5)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from app.config import settings

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def database_path() -> Path:
    return settings.data_dir / "hypatia.db"


def database_url() -> str:
    return f"sqlite+aiosqlite:///{database_path()}"


engine = create_async_engine(database_url())
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


def _alembic_config() -> Config:
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    return cfg


def _upgrade_to_head() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    command.upgrade(_alembic_config(), "head")


async def run_migrations() -> None:
    """Run pending Alembic migrations up to head.

    Alembic's async template internally calls ``asyncio.run(...)``, which
    cannot be invoked from within an already-running event loop (e.g. the
    FastAPI lifespan). Running it in a worker thread gives it a fresh loop.
    """
    await asyncio.to_thread(_upgrade_to_head)
