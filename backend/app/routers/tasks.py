"""Task status REST endpoints (Task 4.7)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.models.schemas import TaskStatusRead
from app.services.task_manager import task_manager

router = APIRouter(prefix="/api/classes/{class_id}/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskStatusRead])
async def list_tasks(class_id: uuid.UUID) -> list[TaskStatusRead]:
    tasks = task_manager.list_tasks(str(class_id))
    return [TaskStatusRead(**t.__dict__) for t in tasks]


@router.get("/{task_id}", response_model=TaskStatusRead)
async def get_task(class_id: uuid.UUID, task_id: str) -> TaskStatusRead:
    t = task_manager.get_status(task_id)
    if t is None or t.class_id != str(class_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return TaskStatusRead(**t.__dict__)


@router.post("/{task_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_task(class_id: uuid.UUID, task_id: str) -> dict[str, str]:
    t = task_manager.get_status(task_id)
    if t is None or t.class_id != str(class_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    task_manager.cancel_task(task_id)
    return {"status": "cancel_requested"}
