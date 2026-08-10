"""Document-to-markdown conversion via MarkItDown (Task 2.2).

Wraps Microsoft's `markitdown <https://github.com/microsoft/markitdown>`_
library to turn documents, spreadsheets, presentations, and images into
markdown. Conversion is best-effort per file: a corrupted or unsupported
input produces a failed :class:`ConversionResult` rather than raising, so
callers (e.g. a background file-processing task) can record the failure on
the ``File`` row instead of crashing the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from markitdown import MarkItDown
from markitdown._exceptions import MarkItDownException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import FileStatus, FileType
from app.services import video_processor
from app.services.summary_generator import generate_document_summary, summary_path_for
from app.services.video_processor import ProcessingResult, update_file_status
from app.utils.logging import get_logger

logger = get_logger()

_converter: MarkItDown | None = None


def _get_converter() -> MarkItDown:
    """Return a lazily-created, process-wide MarkItDown instance.

    MarkItDown's constructor eagerly loads its converter plugins, so it is
    reused across calls instead of being recreated per file.
    """
    global _converter
    if _converter is None:
        _converter = MarkItDown()
    return _converter


@dataclass
class ConversionResult:
    """Result of converting a single file to markdown."""

    success: bool
    markdown_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def convert_document(file_path: Path, output_path: Path) -> ConversionResult:
    """Convert ``file_path`` to markdown and write the result to ``output_path``.

    Supports PDF, DOCX, PPTX, XLSX, CSV, HTML, images (EXIF/OCR), plain text,
    and markdown (passthrough) -- anything MarkItDown's installed converters
    support. On failure (unsupported format, corrupted file), returns a
    :class:`ConversionResult` with ``success=False`` and no file is written.
    """
    try:
        result = _get_converter().convert(file_path)
    except MarkItDownException as exc:
        logger.warning("document_conversion_failed", file=str(file_path), error=str(exc))
        return ConversionResult(success=False, error=str(exc))
    except OSError as exc:
        logger.warning("document_conversion_failed", file=str(file_path), error=str(exc))
        return ConversionResult(success=False, error=str(exc))

    markdown_text = result.markdown
    metadata: dict[str, Any] = {
        "source_filename": file_path.name,
        "source_extension": file_path.suffix.lower(),
        "title": result.title,
        "word_count": len(markdown_text.split()),
        "char_count": len(markdown_text),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown_text, encoding="utf-8")

    logger.info(
        "document_converted",
        file=str(file_path),
        output=str(output_path),
        word_count=metadata["word_count"],
    )
    return ConversionResult(success=True, markdown_text=markdown_text, metadata=metadata)


_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}


def classify_file_type(filename: str) -> FileType:
    """Map a filename extension to a FileType, used both to tag a newly
    uploaded File row and to route it to a pipeline in process_file.
    """
    suffix = Path(filename).suffix.lower()
    if suffix in _VIDEO_EXTENSIONS:
        return FileType.VIDEO
    if suffix in _AUDIO_EXTENSIONS:
        return FileType.AUDIO
    if suffix == ".pdf":
        return FileType.PDF
    if suffix == ".docx":
        return FileType.DOCX
    if suffix == ".pptx":
        return FileType.PPTX
    if suffix == ".xlsx":
        return FileType.XLSX
    if suffix in _IMAGE_EXTENSIONS:
        return FileType.IMAGE
    if suffix in _TEXT_EXTENSIONS:
        return FileType.MARKDOWN
    return FileType.OTHER


def _passthrough_markdown(file_path: Path, output_path: Path) -> ConversionResult:
    """Copy a markdown/text file to converted/ with a small frontmatter header.

    Markdown/text files need no MarkItDown conversion -- passthrough avoids
    MarkItDown reformatting content that is already the target format.
    """
    text = file_path.read_text(encoding="utf-8")
    frontmatter = f"---\nsource: {file_path.name}\ntype: passthrough\n---\n\n"
    markdown_text = frontmatter + text

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown_text, encoding="utf-8")

    metadata: dict[str, Any] = {
        "source_filename": file_path.name,
        "source_extension": file_path.suffix.lower(),
        "word_count": len(text.split()),
        "char_count": len(text),
    }
    return ConversionResult(success=True, markdown_text=markdown_text, metadata=metadata)


async def process_file(
    session: AsyncSession,
    file_id: UUID,
    file_path: Path,
    output_path: Path,
) -> ProcessingResult:
    """Dispatch a File to the right conversion pipeline by extension (Task 2.7).

    Video/audio go to video_processor.process_video, which updates the File
    row itself. Everything else goes through convert_document (MarkItDown) or,
    for markdown/text, the lighter passthrough helper above; either way this
    function updates the File row via update_file_status since convert_document
    has no DB awareness. Never raises: failures are recorded on the File row,
    matching process_video contract.
    """
    file_type = classify_file_type(file_path.name)

    if file_type in (FileType.VIDEO, FileType.AUDIO):
        return await video_processor.process_video(session, file_id, file_path, output_path)

    try:
        if file_type == FileType.MARKDOWN:
            result = _passthrough_markdown(file_path, output_path)
        else:
            result = convert_document(file_path, output_path)
    except OSError as exc:
        result = ConversionResult(success=False, error=str(exc))

    if not result.success:
        await update_file_status(session, file_id, FileStatus.ERROR, error_message=result.error)
        return ProcessingResult(success=False, error=result.error)

    summary_text = generate_document_summary(result.markdown_text, result.metadata, file_path.name)
    summary_path_for(output_path).write_text(summary_text, encoding="utf-8")

    await update_file_status(session, file_id, FileStatus.READY, converted_path=str(output_path))
    return ProcessingResult(success=True, converted_path=output_path, metadata=result.metadata)
