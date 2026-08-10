"""Task 2.2 acceptance: MarkItDown document conversion."""

from __future__ import annotations

import zipfile
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db_models import Base, Class, File, FileStatus, FileType
from app.services import file_converter
from app.services.video_processor import ProcessingResult

# A minimal, hand-written single-page PDF (no external PDF-writing library
# needed) -- the classic minimal-PDF fixture used across the ecosystem.
_MINIMAL_PDF = b"""%PDF-1.1
%\xc2\xa5\xc2\xb1\xc3\xab

1 0 obj
  << /Type /Catalog
     /Pages 2 0 R
  >>
endobj

2 0 obj
  << /Type /Pages
     /Kids [3 0 R]
     /Count 1
     /MediaBox [0 0 300 144]
  >>
endobj

3 0 obj
  <<  /Type /Page
      /Parent 2 0 R
      /Resources
       << /Font
           << /F1
               << /Type /Font
                  /Subtype /Type1
                  /BaseFont /Times-Roman
               >>
           >>
       >>
      /Contents 4 0 R
  >>
endobj

4 0 obj
  << /Length 55 >>
stream
  BT
    /F1 18 Tf
    0 0 Td
    (Hello World) Tj
  ET
endstream
endobj

xref
0 5
0000000000 65535 f 
0000000018 00000 n 
0000000077 00000 n 
0000000178 00000 n 
0000000457 00000 n 
trailer
  <<  /Root 1 0 R
      /Size 5
  >>
startxref
565
%%EOF
"""

_DOCX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

_DOCX_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOCX_DOCUMENT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Hello from a minimal docx.</w:t></w:r></w:p>
  </w:body>
</w:document>"""


def _write_minimal_docx(path: Path) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _DOCX_CONTENT_TYPES)
        z.writestr("_rels/.rels", _DOCX_RELS)
        z.writestr("word/document.xml", _DOCX_DOCUMENT)


def test_convert_plain_text_file(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("Hello world\nSecond line", encoding="utf-8")
    output = tmp_path / "converted" / "notes.md"

    result = file_converter.convert_document(source, output)

    assert result.success is True
    assert result.error is None
    assert "Hello world" in result.markdown_text
    assert output.read_text(encoding="utf-8") == result.markdown_text
    assert result.metadata["source_extension"] == ".txt"
    assert result.metadata["word_count"] == 4


def test_convert_markdown_passthrough(tmp_path: Path) -> None:
    source = tmp_path / "already.md"
    source.write_text("# Title\n\nSome body text.", encoding="utf-8")
    output = tmp_path / "converted" / "already.md"

    result = file_converter.convert_document(source, output)

    assert result.success is True
    assert "Title" in result.markdown_text
    assert output.exists()


def test_convert_creates_output_parent_directories(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("content", encoding="utf-8")
    output = tmp_path / "a" / "b" / "c" / "notes.md"

    result = file_converter.convert_document(source, output)

    assert result.success is True
    assert output.exists()


def test_convert_unsupported_or_corrupted_file_fails_gracefully(tmp_path: Path) -> None:
    source = tmp_path / "garbage.bin"
    source.write_bytes(b"\x00\x01\x02\x03not a real document")
    output = tmp_path / "converted" / "garbage.md"

    result = file_converter.convert_document(source, output)

    assert result.success is False
    assert result.error is not None
    assert result.markdown_text == ""
    assert not output.exists()


def test_convert_missing_file_fails_gracefully(tmp_path: Path) -> None:
    source = tmp_path / "does-not-exist.pdf"
    output = tmp_path / "converted" / "does-not-exist.md"

    result = file_converter.convert_document(source, output)

    assert result.success is False
    assert result.error is not None
    assert not output.exists()


@pytest.mark.integration
def test_convert_sample_pdf(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    source.write_bytes(_MINIMAL_PDF)
    output = tmp_path / "converted" / "sample.md"

    result = file_converter.convert_document(source, output)

    assert result.success is True
    assert "Hello World" in result.markdown_text
    assert output.exists()


@pytest.mark.integration
def test_convert_sample_docx(tmp_path: Path) -> None:
    source = tmp_path / "sample.docx"
    _write_minimal_docx(source)
    output = tmp_path / "converted" / "sample.md"

    result = file_converter.convert_document(source, output)

    assert result.success is True
    assert "Hello from a minimal docx" in result.markdown_text
    assert output.exists()


@pytest.mark.integration
def test_convert_sample_pptx(tmp_path: Path) -> None:
    pptx = pytest.importorskip("pptx")
    source = tmp_path / "sample.pptx"
    presentation = pptx.Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[0])
    slide.shapes.title.text = "Hello from a slide"
    presentation.save(source)
    output = tmp_path / "converted" / "sample.md"

    result = file_converter.convert_document(source, output)

    assert result.success is True
    assert "Hello from a slide" in result.markdown_text
    assert output.exists()


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


async def _make_pending_file(
    session_factory: async_sessionmaker[AsyncSession], filename: str, file_type: FileType
) -> UUID:
    async with session_factory() as session:
        class_ = Class(name="Test Class")
        session.add(class_)
        await session.commit()

        file_ = File(
            class_id=class_.id,
            original_filename=filename,
            file_type=file_type,
            file_size_bytes=10,
            raw_path=f"raw/{filename}",
            status=FileStatus.PENDING,
        )
        session.add(file_)
        await session.commit()
        return file_.id


def test_classify_file_type_table() -> None:
    assert file_converter.classify_file_type("lecture.mp4") == FileType.VIDEO
    assert file_converter.classify_file_type("lecture.mp3") == FileType.AUDIO
    assert file_converter.classify_file_type("notes.pdf") == FileType.PDF
    assert file_converter.classify_file_type("report.docx") == FileType.DOCX
    assert file_converter.classify_file_type("slides.pptx") == FileType.PPTX
    assert file_converter.classify_file_type("sheet.xlsx") == FileType.XLSX
    assert file_converter.classify_file_type("photo.png") == FileType.IMAGE
    assert file_converter.classify_file_type("readme.md") == FileType.MARKDOWN
    assert file_converter.classify_file_type("plain.txt") == FileType.MARKDOWN
    assert file_converter.classify_file_type("mystery.xyz") == FileType.OTHER


async def test_process_file_dispatches_video_to_process_video(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    file_id = await _make_pending_file(session_factory, "lecture.mp4", FileType.VIDEO)
    source = tmp_path / "lecture.mp4"
    source.write_bytes(b"fake video bytes")
    output = tmp_path / "converted" / "lecture.md"

    fake_result = ProcessingResult(success=True, converted_path=output)
    mock_process_video = AsyncMock(return_value=fake_result)
    with patch.object(file_converter.video_processor, "process_video", mock_process_video):
        async with session_factory() as session:
            result = await file_converter.process_file(session, file_id, source, output)

    mock_process_video.assert_called_once()
    assert result is fake_result


async def test_process_file_dispatches_audio_to_process_video(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    file_id = await _make_pending_file(session_factory, "lecture.mp3", FileType.AUDIO)
    source = tmp_path / "lecture.mp3"
    source.write_bytes(b"fake audio bytes")
    output = tmp_path / "converted" / "lecture.md"

    fake_result = ProcessingResult(success=True, converted_path=output)
    mock_process_video = AsyncMock(return_value=fake_result)
    with patch.object(file_converter.video_processor, "process_video", mock_process_video):
        async with session_factory() as session:
            result = await file_converter.process_file(session, file_id, source, output)

    mock_process_video.assert_called_once()
    assert result is fake_result


async def test_process_file_dispatches_markdown_passthrough(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    file_id = await _make_pending_file(session_factory, "notes.md", FileType.MARKDOWN)
    source = tmp_path / "notes.md"
    source.write_text("# Hi" + chr(10) + chr(10) + "Body text.", encoding="utf-8")
    output = tmp_path / "converted" / "notes.md"

    async with session_factory() as session:
        result = await file_converter.process_file(session, file_id, source, output)

    assert result.success is True
    assert output.exists()
    assert "type: passthrough" in output.read_text(encoding="utf-8")

    summary_output = output.with_name("notes.summary.md")
    assert summary_output.exists()
    assert "type: source-summary" in summary_output.read_text(encoding="utf-8")

    async with session_factory() as session:
        file_ = await session.get(File, file_id)
        assert file_ is not None
        assert file_.status == FileStatus.READY
        assert file_.converted_path == str(output)


async def test_process_file_dispatches_documents_to_convert_document(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    file_id = await _make_pending_file(session_factory, "notes.pdf", FileType.PDF)
    source = tmp_path / "notes.pdf"
    source.write_bytes(b"fake pdf bytes")
    output = tmp_path / "converted" / "notes.md"

    fake_result = file_converter.ConversionResult(
        success=True, markdown_text="Hello", metadata={"word_count": 1}
    )

    def _fake_convert_document(src: Path, dst: Path) -> file_converter.ConversionResult:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(fake_result.markdown_text, encoding="utf-8")
        return fake_result

    mock_convert_document = MagicMock(side_effect=_fake_convert_document)
    with patch.object(file_converter, "convert_document", mock_convert_document):
        async with session_factory() as session:
            result = await file_converter.process_file(session, file_id, source, output)

    mock_convert_document.assert_called_once_with(source, output)
    assert result.success is True
    assert output.with_name("notes.summary.md").exists()

    async with session_factory() as session:
        file_ = await session.get(File, file_id)
        assert file_ is not None
        assert file_.status == FileStatus.READY


async def test_process_file_records_error_on_conversion_failure(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    file_id = await _make_pending_file(session_factory, "garbage.bin", FileType.OTHER)
    source = tmp_path / "garbage.bin"
    source.write_bytes(bytes([0, 1, 2, 3]) + b"not a real document")
    output = tmp_path / "converted" / "garbage.md"

    async with session_factory() as session:
        result = await file_converter.process_file(session, file_id, source, output)

    assert result.success is False
    assert result.error is not None
    assert not output.exists()

    async with session_factory() as session:
        file_ = await session.get(File, file_id)
        assert file_ is not None
        assert file_.status == FileStatus.ERROR
        assert file_.error_message == result.error
