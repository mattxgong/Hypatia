"""Task 1.4 acceptance: tables can be created and basic CRUD works."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db_models import Base, ChatMessage, ChatRole, Class, File, FileStatus, FileType
from app.models.schemas import ChatMessageRead, ClassRead, FileRead


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def test_create_class_and_read_back(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        class_ = Class(name="Intro to ML", description="Fall 2026")
        session.add(class_)
        await session.commit()

        result = await session.execute(select(Class).where(Class.name == "Intro to ML"))
        fetched = result.scalar_one()

        assert fetched.id == class_.id
        assert ClassRead.model_validate(fetched).name == "Intro to ML"


async def test_file_and_chat_message_crud(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        class_ = Class(name="Data Structures")
        session.add(class_)
        await session.commit()

        file_ = File(
            class_id=class_.id,
            original_filename="lecture-1.pdf",
            file_type=FileType.PDF,
            file_size_bytes=1024,
            raw_path="raw/lecture-1.pdf",
            status=FileStatus.PENDING,
        )
        message = ChatMessage(class_id=class_.id, role=ChatRole.USER, content="Summarize lecture 1")
        session.add_all([file_, message])
        await session.commit()

        fetched_file = (
            await session.execute(select(File).where(File.class_id == class_.id))
        ).scalar_one()
        assert FileRead.model_validate(fetched_file).original_filename == "lecture-1.pdf"

        fetched_message = (
            await session.execute(select(ChatMessage).where(ChatMessage.class_id == class_.id))
        ).scalar_one()
        assert ChatMessageRead.model_validate(fetched_message).content == "Summarize lecture 1"

        await session.delete(fetched_file)
        await session.commit()

        remaining = (
            (await session.execute(select(File).where(File.class_id == class_.id))).scalars().all()
        )
        assert remaining == []
