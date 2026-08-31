"""Tests for TaskManager (Task 3B.12)."""

from __future__ import annotations

from app.services.task_manager import TaskManager


def test_start_task():
    tm = TaskManager()
    task_id = tm.start_task("rebuild", "class-1")
    t = tm.get_status(task_id)
    assert t is not None
    assert t.operation == "rebuild"
    assert t.class_id == "class-1"
    assert t.status == "running"
    assert t.progress == 0


def test_update_progress():
    tm = TaskManager()
    task_id = tm.start_task("rebuild", "class-1")
    tm.update_progress(task_id, 50, "Halfway there")
    t = tm.get_status(task_id)
    assert t is not None
    assert t.progress == 50
    assert t.message == "Halfway there"


def test_complete_task():
    tm = TaskManager()
    task_id = tm.start_task("lint", "class-2")
    tm.complete_task(task_id)
    t = tm.get_status(task_id)
    assert t is not None
    assert t.status == "complete"
    assert t.progress == 100


def test_fail_task():
    tm = TaskManager()
    task_id = tm.start_task("rebuild", "class-1")
    tm.fail_task(task_id, "LLM timeout")
    t = tm.get_status(task_id)
    assert t is not None
    assert t.status == "failed"
    assert t.error == "LLM timeout"


def test_cancel_task():
    tm = TaskManager()
    task_id = tm.start_task("rebuild", "class-1")
    tm.cancel_task(task_id)
    assert tm.is_cancelled(task_id) is True
    t = tm.get_status(task_id)
    assert t is not None
    assert t.status == "cancelled"


def test_cancel_noop_after_complete():
    tm = TaskManager()
    task_id = tm.start_task("rebuild", "class-1")
    tm.complete_task(task_id)
    tm.cancel_task(task_id)
    t = tm.get_status(task_id)
    assert t is not None
    assert t.status == "complete"


def test_list_tasks():
    tm = TaskManager()
    tm.start_task("rebuild", "class-1")
    tm.start_task("lint", "class-1")
    tm.start_task("export", "class-2")
    assert len(tm.list_tasks()) == 3
    assert len(tm.list_tasks("class-1")) == 2
    assert len(tm.list_tasks("class-2")) == 1


def test_get_status_nonexistent():
    tm = TaskManager()
    assert tm.get_status("nonexistent") is None
    assert tm.is_cancelled("nonexistent") is False
