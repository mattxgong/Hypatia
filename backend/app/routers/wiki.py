"""Wiki router: tree, page CRUD, search, export, lint, rebuild (Task 4.4)."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory, get_session
from app.dependencies import check_llm_available
from app.models.db_models import WikiPage
from app.models.schemas import (
    WikiPageRead,
    WikiPageUpdate,
    WikiSearchResponse,
    WikiSearchResultRead,
    WikiTreeNodeRead,
)
from app.services import wiki_engine
from app.services.task_manager import task_manager
from app.services.wiki_search import (
    SearchMode,
    count_wiki_search_results,
    hybrid_search,
)
from app.utils.logging import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/classes/{class_id}/wiki", tags=["wiki"])


@router.get("/tree", response_model=list[WikiTreeNodeRead])
async def get_wiki_tree(
    class_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[WikiTreeNodeRead]:
    nodes = await wiki_engine.get_wiki_tree(session, class_id)
    return [WikiTreeNodeRead(**asdict(n)) for n in nodes]


@router.get("/index")
async def get_wiki_index(
    class_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    page = await wiki_engine.get_wiki_page(session, class_id, "index.md")
    if page is None:
        return {"content": ""}
    return {"content": page.content}


@router.get("/pages/{page_path:path}", response_model=WikiPageRead)
async def get_wiki_page(
    class_id: uuid.UUID, page_path: str, session: AsyncSession = Depends(get_session)
) -> WikiPageRead:
    result = await session.execute(
        select(WikiPage).where(WikiPage.class_id == class_id, WikiPage.path == page_path)
    )
    db_page = result.scalar_one_or_none()
    if db_page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wiki page not found")
    return WikiPageRead.model_validate(db_page)


@router.put("/pages/{page_path:path}", response_model=WikiPageRead)
async def update_wiki_page(
    class_id: uuid.UUID,
    page_path: str,
    body: WikiPageUpdate,
    session: AsyncSession = Depends(get_session),
) -> WikiPageRead:
    await wiki_engine.update_wiki_page(
        session, class_id, page_path, body.content, is_user_edit=True
    )

    result = await session.execute(
        select(WikiPage).where(WikiPage.class_id == class_id, WikiPage.path == page_path)
    )
    db_page = result.scalar_one_or_none()
    if db_page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wiki page not found")
    return WikiPageRead.model_validate(db_page)


@router.get("/search", response_model=WikiSearchResponse)
async def search_wiki(
    class_id: uuid.UUID,
    q: str = Query(..., min_length=1),
    category: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    mode: SearchMode = Query("hybrid"),  # noqa: B008
    session: AsyncSession = Depends(get_session),
) -> WikiSearchResponse:
    results = await hybrid_search(
        session, class_id, q, limit=limit, category=category, offset=offset, mode=mode
    )
    total_count = await count_wiki_search_results(session, class_id, q, category=category)
    return WikiSearchResponse(
        results=[
            WikiSearchResultRead(
                page_id=r.page_id,
                class_id=r.class_id,
                path=r.path,
                title=r.title,
                category=r.category,
                rank=r.rank,
                snippet=r.snippet,
            )
            for r in results
        ],
        total_count=total_count,
    )


@router.post("/export")
async def export_wiki(
    class_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> FileResponse:
    result = await wiki_engine.handle_export(session, class_id)
    if not result.success or not result.export_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error or "Export failed",
        )
    return FileResponse(
        result.export_path,
        filename=Path(result.export_path).name,
        media_type="application/zip",
    )


@router.post("/lint", dependencies=[Depends(check_llm_available)])
async def lint_wiki(class_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> dict:
    result = await wiki_engine.handle_lint(session, class_id)
    return {
        "success": result.success,
        "issues": [asdict(i) for i in result.issues],
        "error": result.error,
    }


async def _run_rebuild(class_id: uuid.UUID, task_id: str) -> None:
    async with async_session_factory() as session:
        try:
            result = await wiki_engine.handle_rebuild(session, class_id, task_id=task_id)
            if result.success:
                task_manager.complete_task(task_id)
            else:
                task_manager.fail_task(task_id, result.error or "Rebuild failed")
        except Exception as e:  # noqa: BLE001
            task_manager.fail_task(task_id, str(e))


@router.post("/rebuild", dependencies=[Depends(check_llm_available)])
async def rebuild_wiki(
    class_id: uuid.UUID,
    confirm: bool = Query(False),
    background_tasks: BackgroundTasks = BackgroundTasks(),  # noqa: B008
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not confirm:
        preview = await wiki_engine.handle_rebuild_preview(session, class_id)
        return asdict(preview)

    task_id = task_manager.start_task("rebuild", str(class_id))
    background_tasks.add_task(_run_rebuild, class_id, task_id)
    return {"task_id": task_id, "status": "started"}
