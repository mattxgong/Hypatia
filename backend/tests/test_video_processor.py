"""Task 2.3-2.6 acceptance: video/audio to timestamped transcript pipeline."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db_models import Base, Class, File, FileStatus, FileType
from app.services import video_processor
from app.services.video_processor import (
    FfmpegNotAvailableError,
    TranscriptionResult,
    TranscriptSegment,
)


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


async def _make_pending_file(session_factory: async_sessionmaker[AsyncSession]) -> UUID:
    async with session_factory() as session:
        class_ = Class(name="Signals and Systems")
        session.add(class_)
        await session.commit()

        file_ = File(
            class_id=class_.id,
            original_filename="lecture-1.mp4",
            file_type=FileType.VIDEO,
            file_size_bytes=2048,
            raw_path="raw/lecture-1.mp4",
            status=FileStatus.PENDING,
        )
        session.add(file_)
        await session.commit()
        return file_.id


def test_format_timestamp() -> None:
    assert video_processor.format_timestamp(0) == "00:00:00"
    assert video_processor.format_timestamp(65) == "00:01:05"
    assert video_processor.format_timestamp(3725) == "01:02:05"


def test_generate_transcript_markdown_includes_deep_links() -> None:
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="Welcome to the lecture."),
        TranscriptSegment(start=5.0, end=12.5, text="Today we cover Fourier transforms."),
    ]

    markdown = video_processor.generate_transcript_markdown(segments, "lecture-1.mp4")

    assert "source: lecture-1.mp4" in markdown
    assert "type: transcript" in markdown
    assert "duration: 00:00:12" in markdown
    assert "hypatia://open?file=lecture-1.mp4&t=0" in markdown
    assert "hypatia://open?file=lecture-1.mp4&t=5" in markdown
    assert "Welcome to the lecture." in markdown
    assert "Today we cover Fourier transforms." in markdown


def test_generate_transcript_markdown_empty_segments() -> None:
    markdown = video_processor.generate_transcript_markdown([], "silence.mp4")

    assert "duration: 00:00:00" in markdown
    assert "# Transcript: silence.mp4" in markdown


def test_extract_audio_raises_when_ffmpeg_unavailable(tmp_path: Path) -> None:
    with (
        patch.object(video_processor, "_FFMPEG_AVAILABLE", False),
        patch.object(video_processor, "_FFPROBE_AVAILABLE", False),
        pytest.raises(FfmpegNotAvailableError),
    ):
        video_processor.extract_audio(tmp_path / "in.mp4", tmp_path / "out.wav")


def test_transcribe_audio_uses_configured_model_size(tmp_path: Path) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake")

    fake_segment = MagicMock(start=1.0, end=2.0, text=" hello ")
    fake_info = MagicMock(language="en", language_probability=0.99)
    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([fake_segment], fake_info)

    with patch.object(video_processor, "_get_whisper_model", return_value=fake_model) as get_model:
        result = video_processor.transcribe_audio(audio_path)

    get_model.assert_called_once_with("base")
    assert isinstance(result, TranscriptionResult)
    assert result.segments == [TranscriptSegment(start=1.0, end=2.0, text="hello")]
    assert result.language == "en"
    assert result.language_probability == 0.99


def test_transcribe_audio_explicit_model_size_overrides_default(tmp_path: Path) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake")
    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([], MagicMock(language=None, language_probability=None))

    with patch.object(video_processor, "_get_whisper_model", return_value=fake_model) as get_model:
        video_processor.transcribe_audio(audio_path, model_size="small")

    get_model.assert_called_once_with("small")


async def test_process_video_success_updates_file_status(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    file_id = await _make_pending_file(session_factory)
    source = tmp_path / "lecture-1.mp4"
    source.write_bytes(b"fake video bytes")
    output = tmp_path / "converted" / "lecture-1.md"

    fake_metadata = video_processor.VideoMetadata(duration_seconds=12.5, width=640, height=480)
    fake_transcription = TranscriptionResult(
        segments=[TranscriptSegment(start=0.0, end=1.0, text="Hello")], language="en"
    )

    with (
        patch.object(
            video_processor, "extract_audio", return_value=(tmp_path / "audio.wav", fake_metadata)
        ) as extract,
        patch.object(video_processor, "transcribe_audio", return_value=fake_transcription),
    ):
        async with session_factory() as session:
            result = await video_processor.process_video(session, file_id, source, output)

    extract.assert_called_once()
    assert result.success is True
    assert result.converted_path == output
    assert output.exists()
    assert "Hello" in output.read_text(encoding="utf-8")
    assert output.with_suffix(".metadata.json").exists()

    summary_output = output.with_name("lecture-1.summary.md")
    assert summary_output.exists()
    assert "type: source-summary" in summary_output.read_text(encoding="utf-8")

    async with session_factory() as session:
        file_ = await session.get(File, file_id)
        assert file_ is not None
        assert file_.status == FileStatus.READY
        assert file_.converted_path == str(output)


async def test_process_video_failure_records_error_on_file(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    file_id = await _make_pending_file(session_factory)
    source = tmp_path / "lecture-1.mp4"
    source.write_bytes(b"fake video bytes")
    output = tmp_path / "converted" / "lecture-1.md"

    with patch.object(
        video_processor, "extract_audio", side_effect=RuntimeError("ffmpeg exploded")
    ):
        async with session_factory() as session:
            result = await video_processor.process_video(session, file_id, source, output)

    assert result.success is False
    assert result.error == "ffmpeg exploded"
    assert not output.exists()

    async with session_factory() as session:
        file_ = await session.get(File, file_id)
        assert file_ is not None
        assert file_.status == FileStatus.ERROR
        assert file_.error_message == "ffmpeg exploded"


async def test_process_video_cleans_up_intermediate_wav(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    file_id = await _make_pending_file(session_factory)
    source = tmp_path / "lecture-1.mp4"
    source.write_bytes(b"fake video bytes")
    output = tmp_path / "converted" / "lecture-1.md"
    tmp_wav = output.with_suffix(".wav")

    def _fake_extract_audio(
        video_path: Path, output_path: Path
    ) -> tuple[Path, video_processor.VideoMetadata]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"wav bytes")
        return output_path, video_processor.VideoMetadata(duration_seconds=1.0)

    with (
        patch.object(video_processor, "extract_audio", side_effect=_fake_extract_audio),
        patch.object(
            video_processor,
            "transcribe_audio",
            return_value=TranscriptionResult(segments=[]),
        ),
    ):
        async with session_factory() as session:
            await video_processor.process_video(session, file_id, source, output)

    assert not tmp_wav.exists()


@pytest.mark.integration
def test_extract_audio_real_ffmpeg_video_source(tmp_path: Path) -> None:
    import subprocess

    source = tmp_path / "synthetic.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=320x240:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-shortest",
            "-y",
            str(source),
        ],
        capture_output=True,
        check=True,
    )
    output = tmp_path / "audio.wav"

    wav_path, metadata = video_processor.extract_audio(source, output)

    assert wav_path == output
    assert output.exists()
    assert metadata.duration_seconds == pytest.approx(2.0, abs=0.5)
    assert metadata.width == 320
    assert metadata.height == 240


@pytest.mark.integration
def test_extract_audio_real_ffmpeg_audio_only_source(tmp_path: Path) -> None:
    import subprocess

    source = tmp_path / "synthetic.wav"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-y", str(source)],
        capture_output=True,
        check=True,
    )
    output = tmp_path / "audio.wav"

    _, metadata = video_processor.extract_audio(source, output)

    assert output.exists()
    assert metadata.duration_seconds == pytest.approx(1.0, abs=0.5)
    assert metadata.width is None
    assert metadata.height is None


@pytest.mark.integration
def test_transcribe_audio_real_model_on_synthetic_tone(tmp_path: Path) -> None:
    import subprocess

    source = tmp_path / "tone.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-y",
            str(source),
        ],
        capture_output=True,
        check=True,
    )

    result = video_processor.transcribe_audio(source, model_size="base")

    assert isinstance(result, TranscriptionResult)
    assert result.language is not None
