"""Tests for TaskManager (Task 3B.12)."""

from __future__ import annotations

from app.services.task_manager import TaskManager


def test_start_task():
    tm = TaskManager()
    task_id = tm.start_task("rebuild", "class-1")
    status = tm.get_status(task_id)
    assert status is not None
    assert status.operation == "rebuild"
    assert status.class_id == "class-1"
    assert status.state == "running"
    assert status.percent == 0


def test_update_progress():
    tm = TaskManager()
    task_id = tm.start_task("rebuild", "class-1")
    tm.update_progress(task_id, 50, "Halfway there")
    status = tm.get_status(task_id)
    assert status is not None
    assert status.percent == 50
    assert status.message == "Halfway there"


def test_complete_task():
    tm = TaskManager()
    task_id = tm.start_task("lint", "class-2")
    tm.complete_task(task_id)
    status = tm.get_status(task_id)
    assert status is not None
    assert status.state == "complete"
    assert status.percent == 100


def test_fail_task():
    tm = TaskManager()
    task_id = tm.start_task("rebuild", "class-1")
    tm.fail_task(task_id, "LLM timeout")
    status = tm.get_status(task_id)
    assert status is not None
    assert status.state == "failed"
    assert status.error == "LLM timeout"


def test_cancel_task():
    tm = TaskManager()
    task_id = tm.start_task("rebuild", "class-1")
    tm.cancel_task(task_id)
    assert tm.is_cancelled(task_id) is True
    status = tm.get_status(task_id)
    assert status is not None
    assert status.state == "cancelled"


def test_cancel_noop_after_complete():
    tm = TaskManager()
    task_id = tm.start_task("rebuild", "class-1")
    tm.complete_task(task_id)
    tm.cancel_task(task_id)
    status = tm.get_status(task_id)
    assert status is not None
    assert status.state == "complete"


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
