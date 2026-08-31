"""Classes CRUD router (Task 4.2)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.errors import ResourceNotFoundError
from app.models.db_models import Class, File, WikiPage
from app.models.schemas import ClassCreate, ClassRead, ClassReadWithStats, ClassUpdate
from app.services import storage_service
from app.services.wiki_git import init_wiki_repo
from app.utils.logging import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/classes", tags=["classes"])


@router.post("", response_model=ClassRead, status_code=status.HTTP_201_CREATED)
async def create_class(
    body: ClassCreate, session: AsyncSession = Depends(get_session)
) -> ClassRead:
    class_ = Class(name=body.name, description=body.description)
    session.add(class_)
    await session.commit()
    await session.refresh(class_)

    storage_service.create_class_directories(str(class_.id))
    init_wiki_repo(str(class_.id))

    logger.info("class_created", class_id=str(class_.id), name=body.name)
    return ClassRead.model_validate(class_)


@router.get("", response_model=list[ClassReadWithStats])
async def list_classes(
    session: AsyncSession = Depends(get_session),
) -> list[ClassReadWithStats]:
    file_count_sub = (
        select(func.count()).select_from(File).where(File.class_id == Class.id).correlate(Class)
    ).scalar_subquery()
    page_count_sub = (
        select(func.count())
        .select_from(WikiPage)
        .where(WikiPage.class_id == Class.id)
        .correlate(Class)
    ).scalar_subquery()

    result = await session.execute(
        select(
            Class,
            file_count_sub.label("file_count"),
            page_count_sub.label("page_count"),
        ).order_by(Class.created_at.desc())
    )
    return [
        ClassReadWithStats(
            **ClassRead.model_validate(row[0]).model_dump(),
            file_count=row[1] or 0,
            page_count=row[2] or 0,
        )
        for row in result.all()
    ]


@router.get("/{class_id}", response_model=ClassReadWithStats)
async def get_class(
    class_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> ClassReadWithStats:
    class_ = await session.get(Class, class_id)
    if class_ is None:
        raise ResourceNotFoundError("Class not found")

    file_count_result = await session.execute(
        select(func.count()).select_from(File).where(File.class_id == class_id)
    )
    page_count_result = await session.execute(
        select(func.count()).select_from(WikiPage).where(WikiPage.class_id == class_id)
    )

    data = ClassRead.model_validate(class_).model_dump()
    data["file_count"] = file_count_result.scalar() or 0
    data["page_count"] = page_count_result.scalar() or 0
    return ClassReadWithStats(**data)


@router.put("/{class_id}", response_model=ClassRead)
async def update_class(
    class_id: uuid.UUID, body: ClassUpdate, session: AsyncSession = Depends(get_session)
) -> ClassRead:
    class_ = await session.get(Class, class_id)
    if class_ is None:
        raise ResourceNotFoundError("Class not found")

    if body.name is not None:
        class_.name = body.name
    if body.description is not None:
        class_.description = body.description

    await session.commit()
    await session.refresh(class_)
    logger.info("class_updated", class_id=str(class_id))
    return ClassRead.model_validate(class_)


@router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_class(class_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> None:
    class_ = await session.get(Class, class_id)
    if class_ is None:
        raise ResourceNotFoundError("Class not found")

    await session.delete(class_)
    await session.commit()

    storage_service.delete_class_directory(str(class_id))
    logger.info("class_deleted", class_id=str(class_id))
