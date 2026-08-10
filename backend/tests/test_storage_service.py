"""Task 2.1 acceptance: save, retrieve, and delete files; directories are
created correctly."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import storage_service


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage_service.settings, "data_dir", tmp_path)


def test_create_class_directories_creates_full_tree() -> None:
    root = storage_service.create_class_directories("class-1")

    assert root.is_dir()
    for subdir in ("raw", "converted", "wiki", "thumbnails"):
        assert (root / subdir).is_dir()


def test_create_class_directories_is_idempotent() -> None:
    storage_service.create_class_directories("class-1")
    root = storage_service.create_class_directories("class-1")

    assert root.is_dir()


def test_save_and_get_raw_file_round_trip() -> None:
    saved_path = storage_service.save_raw_file("class-1", "lecture.pdf", b"pdf-bytes")

    assert saved_path == storage_service.get_raw_path("class-1", "lecture.pdf")
    assert saved_path.read_bytes() == b"pdf-bytes"


def test_save_raw_file_creates_directories_on_demand() -> None:
    saved_path = storage_service.save_raw_file("class-2", "notes.txt", b"hello")

    assert saved_path.parent == storage_service.raw_dir("class-2")
    assert saved_path.parent.is_dir()


def test_save_raw_file_handles_filename_collision() -> None:
    first = storage_service.save_raw_file("class-1", "lecture.pdf", b"first")
    second = storage_service.save_raw_file("class-1", "lecture.pdf", b"second")

    assert first != second
    assert second.name == "lecture-1.pdf"
    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"


def test_save_raw_file_handles_repeated_collisions() -> None:
    storage_service.save_raw_file("class-1", "lecture.pdf", b"0")
    storage_service.save_raw_file("class-1", "lecture.pdf", b"1")
    third = storage_service.save_raw_file("class-1", "lecture.pdf", b"2")

    assert third.name == "lecture-2.pdf"


def test_save_raw_file_sanitizes_path_traversal_attempt() -> None:
    saved_path = storage_service.save_raw_file("class-1", "../../etc/passwd", b"pwned")

    assert saved_path.parent == storage_service.raw_dir("class-1")
    assert saved_path.name == "passwd"
    assert saved_path.read_bytes() == b"pwned"


def test_save_raw_file_sanitizes_windows_style_path_traversal() -> None:
    saved_path = storage_service.save_raw_file("class-1", "..\\..\\Windows\\evil.dll", b"pwned")

    assert saved_path.parent == storage_service.raw_dir("class-1")
    assert saved_path.name == "evil.dll"


def test_resolve_raw_path_rejects_degenerate_filename() -> None:
    with pytest.raises(ValueError):
        storage_service.resolve_raw_path("class-1", "..")

    with pytest.raises(ValueError):
        storage_service.resolve_raw_path("class-1", ".")


def test_get_converted_path_resolves_under_converted_dir() -> None:
    path = storage_service.get_converted_path("class-1", "lecture.md")

    assert path == storage_service.converted_dir("class-1") / "lecture.md"


def test_delete_file_removes_raw_and_converted_artifacts() -> None:
    storage_service.save_raw_file("class-1", "lecture.pdf", b"raw")
    converted_dir = storage_service.converted_dir("class-1")
    converted_dir.mkdir(parents=True, exist_ok=True)
    (converted_dir / "lecture.md").write_text("converted")
    (converted_dir / "lecture.summary.md").write_text("summary")
    (converted_dir / "lecture.metadata.json").write_text("{}")
    (converted_dir / "other.md").write_text("unrelated")

    storage_service.delete_file("class-1", "lecture.pdf")

    assert not storage_service.get_raw_path("class-1", "lecture.pdf").exists()
    assert not (converted_dir / "lecture.md").exists()
    assert not (converted_dir / "lecture.summary.md").exists()
    assert not (converted_dir / "lecture.metadata.json").exists()
    assert (converted_dir / "other.md").exists()


def test_delete_file_is_noop_when_nothing_exists() -> None:
    storage_service.delete_file("class-1", "missing.pdf")


def test_delete_class_directory_removes_entire_tree() -> None:
    root = storage_service.create_class_directories("class-1")
    storage_service.save_raw_file("class-1", "lecture.pdf", b"raw")

    storage_service.delete_class_directory("class-1")

    assert not root.exists()


def test_delete_class_directory_is_noop_when_missing() -> None:
    storage_service.delete_class_directory("nonexistent-class")
