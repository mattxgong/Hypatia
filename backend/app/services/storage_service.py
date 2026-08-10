"""Per-Class file storage on disk (Task 2.1).

Every Class owns a directory tree at
``data_dir/classes/{class_id}/{raw,converted,wiki,thumbnails}``:

- ``raw/`` -- uploaded source files, unmodified.
- ``converted/`` -- markdown conversions, summaries, and metadata sidecars
  produced by ``file_converter``/``video_processor``.
- ``wiki/`` -- the Class's wiki, owned and versioned by ``wiki_git``.
- ``thumbnails/`` -- generated preview images (later phase).

This module only manages the ``raw/`` and ``converted/`` sides; it does not
touch ``wiki/`` (owned by :mod:`app.services.wiki_git`, which creates that
directory itself as a git repo).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger()

_CLASS_SUBDIRS = ("raw", "converted", "wiki", "thumbnails")


def class_dir(class_id: str) -> Path:
    """Return the root data directory for a Class, without creating it."""
    return settings.data_dir / "classes" / class_id


def raw_dir(class_id: str) -> Path:
    """Return the ``raw/`` directory for a Class, without creating it."""
    return class_dir(class_id) / "raw"


def converted_dir(class_id: str) -> Path:
    """Return the ``converted/`` directory for a Class, without creating it."""
    return class_dir(class_id) / "converted"


def create_class_directories(class_id: str) -> Path:
    """Create the full ``raw/converted/wiki/thumbnails`` tree for a Class.

    Returns the Class's root directory. Safe to call repeatedly.
    """
    root = class_dir(class_id)
    for subdir in _CLASS_SUBDIRS:
        (root / subdir).mkdir(parents=True, exist_ok=True)
    return root


def _sanitize_filename(filename: str) -> str:
    """Reduce ``filename`` to a bare file name with no directory components.

    Guards against path traversal (``"../../etc/passwd"``) and absolute
    paths (``"/etc/passwd"``, ``"C:\\Windows\\..."``) from reaching disk
    operations, by keeping only the final path segment. Raises ValueError
    if nothing safe remains (e.g. the input was ``"."``, ``".."``, or a
    trailing-slash-only string).
    """
    name = Path(filename.replace("\\", "/")).name
    if not name or name in (".", ".."):
        raise ValueError(f"invalid filename: {filename!r}")
    return name


def _next_available_path(path: Path) -> Path:
    """If ``path`` already exists, return a sibling path with a numeric
    suffix inserted before the extension (``name-1.ext``, ``name-2.ext``,
    ...) that does not exist yet. Otherwise return ``path`` unchanged."""
    if not path.exists():
        return path

    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def resolve_raw_path(class_id: str, filename: str) -> Path:
    """Resolve (and create directories for) the path a raw upload should be
    written to, without writing any file content.

    ``filename`` is sanitized to its bare name (no directory components),
    guarding against path traversal. If it already exists in ``raw/``, a
    numeric suffix is appended to avoid overwriting the existing file.
    """
    create_class_directories(class_id)
    safe_filename = _sanitize_filename(filename)
    path = _next_available_path(raw_dir(class_id) / safe_filename)
    if path.name != filename:
        logger.info(
            "raw_filename_collision",
            class_id=class_id,
            requested=filename,
            saved_as=path.name,
        )
    return path


def save_raw_file(class_id: str, filename: str, file_bytes: bytes) -> Path:
    """Save uploaded file bytes under ``raw/`` for a Class.

    See :func:`resolve_raw_path` for filename sanitization and collision
    handling. Returns the path the file was actually written to.
    """
    path = resolve_raw_path(class_id, filename)
    path.write_bytes(file_bytes)
    return path


def get_raw_path(class_id: str, filename: str) -> Path:
    """Resolve the full path to a raw file, without checking it exists."""
    return raw_dir(class_id) / _sanitize_filename(filename)


def get_converted_path(class_id: str, filename: str) -> Path:
    """Resolve the full path where a converted output should be written or
    read, without checking it exists."""
    return converted_dir(class_id) / filename


def delete_class_directory(class_id: str) -> None:
    """Remove the entire data tree for a Class (raw, converted, wiki,
    thumbnails). No-op if the directory does not exist."""
    root = class_dir(class_id)
    if root.exists():
        shutil.rmtree(root)
        logger.info("class_directory_deleted", class_id=class_id)


def delete_file(class_id: str, filename: str) -> None:
    """Remove a raw file and every converted artifact derived from it
    (``{stem}.md``, ``{stem}.summary.md``, ``{stem}.metadata.json``, ...).
    No-op for any path that does not exist."""
    raw_path = get_raw_path(class_id, filename)
    raw_path.unlink(missing_ok=True)

    stem = Path(filename).stem
    conv_dir = converted_dir(class_id)
    if conv_dir.exists():
        for artifact in conv_dir.glob(f"{stem}*"):
            artifact.unlink(missing_ok=True)
