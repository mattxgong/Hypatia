"""In-memory task registry for long-running operations (Task 3B.12).

Tracks progress of operations like /rebuild and /lint so the frontend can
poll status and the user can cancel mid-operation. Tasks are ephemeral —
they do not survive backend restarts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal


@dataclass
class TaskStatus:
    """Current state of a tracked background task."""

    task_id: str
    operation: str
    class_id: str
    percent: int = 0
    message: str = ""
    state: Literal["running", "complete", "failed", "cancelled"] = "running"
    error: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))


class TaskManager:
    """Singleton task registry for long-running operations."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskStatus] = {}

    def start_task(self, operation: str, class_id: str) -> str:
        """Register a new running task. Returns the task_id."""
        task_id = str(uuid.uuid4())
        self._tasks[task_id] = TaskStatus(
            task_id=task_id,
            operation=operation,
            class_id=class_id,
            message=f"Starting {operation}...",
        )
        return task_id

    def update_progress(self, task_id: str, percent: int, message: str) -> None:
        """Update a running task's progress."""
        task = self._tasks.get(task_id)
        if task and task.state == "running":
            task.percent = percent
            task.message = message

    def cancel_task(self, task_id: str) -> None:
        """Request cancellation of a running task."""
        task = self._tasks.get(task_id)
        if task and task.state == "running":
            task.state = "cancelled"
            task.message = "Cancelled by user"

    def complete_task(self, task_id: str) -> None:
        """Mark a task as successfully completed."""
        task = self._tasks.get(task_id)
        if task and task.state == "running":
            task.state = "complete"
            task.percent = 100
            task.message = "Complete"

    def fail_task(self, task_id: str, error: str) -> None:
        """Mark a task as failed."""
        task = self._tasks.get(task_id)
        if task and task.state == "running":
            task.state = "failed"
            task.error = error
            task.message = f"Failed: {error}"

    def is_cancelled(self, task_id: str) -> bool:
        """Check if a task has been cancelled (operations should check periodically)."""
        task = self._tasks.get(task_id)
        return task is not None and task.state == "cancelled"

    def get_status(self, task_id: str) -> TaskStatus | None:
        """Get the current status of a task."""
        return self._tasks.get(task_id)

    def list_tasks(self, class_id: str | None = None) -> list[TaskStatus]:
        """List all tasks, optionally filtered by class_id."""
        tasks = list(self._tasks.values())
        if class_id:
            tasks = [t for t in tasks if t.class_id == class_id]
        return tasks

    def cleanup_completed(self, max_age_seconds: int = 3600) -> None:
        """Remove completed/failed/cancelled tasks older than max_age_seconds."""
        now = datetime.now(UTC)
        to_remove = []
        for task_id, task in self._tasks.items():
            if task.state in ("complete", "failed", "cancelled"):
                started = datetime.fromisoformat(task.started_at)
                if (now - started).total_seconds() > max_age_seconds:
                    to_remove.append(task_id)
        for task_id in to_remove:
            del self._tasks[task_id]


task_manager = TaskManager()
