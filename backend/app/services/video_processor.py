"""Video/audio -> timestamped transcript pipeline (Tasks 2.3-2.6).

Turns an uploaded video or audio file into a markdown transcript with
per-segment timestamps and a hypatia://open deep-link the frontend can
use to jump a player to that moment. Three independently callable stages:

1. extract_audio -- ffmpeg pulls a 16kHz mono WAV out of the source file
   (video or audio; ffmpeg handles either transparently) and ffprobe reads
   duration/resolution/codec/fps metadata.
2. transcribe_audio -- faster-whisper turns the WAV into timestamped
   text segments.
3. generate_transcript_markdown -- renders those segments into the final
   markdown document (with YAML frontmatter).

process_video orchestrates all three, writes the markdown and metadata
sidecar to converted/, deletes the intermediate WAV, and updates the
File row status. Like file_converter, pipeline failures are caught
and recorded on the File row rather than raised, so a background worker can
report the error instead of crashing.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

from faster_whisper import WhisperModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.db_models import File, FileStatus
from app.utils.logging import get_logger

logger = get_logger()


_FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
_FFPROBE_AVAILABLE = shutil.which("ffprobe") is not None
_warned_ffmpeg_missing = False

_whisper_models: dict[str, WhisperModel] = {}


class FfmpegNotAvailableError(RuntimeError):
    """Raised when ffmpeg/ffprobe is required but not installed."""


def _warn_ffmpeg_missing() -> None:
    global _warned_ffmpeg_missing
    if not _warned_ffmpeg_missing:
        logger.warning("ffmpeg_not_found", detail="video/audio processing is disabled")
        _warned_ffmpeg_missing = True


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


@dataclass
class VideoMetadata:
    """Metadata probed from a video/audio file via ffprobe.

    width/height/codec/frame_rate are None for audio-only inputs, since
    there is no video stream to probe.
    """

    duration_seconds: float
    width: int | None = None
    height: int | None = None
    codec: str | None = None
    frame_rate: float | None = None


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    segments: list[TranscriptSegment]
    language: str | None = None
    language_probability: float | None = None


@dataclass
class ProcessingResult:
    success: bool
    converted_path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def _probe_metadata(path: Path) -> VideoMetadata:
    """Probe duration (always) plus resolution/codec/fps (video streams
    only) via ffprobe. Any field ffprobe cannot determine is left None.
    """
    format_result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    try:
        duration = float(format_result.stdout.strip())
    except ValueError:
        duration = 0.0

    stream_result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,codec_name,r_frame_rate",
            "-of",
            "json",
            str(path),
        ]
    )
    width = height = frame_rate = None
    codec = None
    try:
        streams = json.loads(stream_result.stdout or "{}").get("streams", [])
    except json.JSONDecodeError:
        streams = []
    if streams:
        stream = streams[0]
        width = stream.get("width")
        height = stream.get("height")
        codec = stream.get("codec_name")
        rate = stream.get("r_frame_rate", "")
        if "/" in rate:
            num, _, denom = rate.partition("/")
            try:
                frame_rate = float(num) / float(denom) if float(denom) else None
            except ValueError:
                frame_rate = None

    return VideoMetadata(
        duration_seconds=duration,
        width=width,
        height=height,
        codec=codec,
        frame_rate=frame_rate,
    )


def extract_audio(video_path: Path, output_path: Path) -> tuple[Path, VideoMetadata]:
    """Extract 16kHz mono WAV audio from video_path via ffmpeg.

    Works uniformly for video and audio-only inputs (mp3, m4a, wav, ...);
    ffmpeg decodes either. Returns the WAV path and probed metadata
    (duration always populated; resolution/codec/fps are None when the
    input has no video stream).

    Raises FfmpegNotAvailableError if ffmpeg/ffprobe is not on PATH.
    """
    if not _FFMPEG_AVAILABLE or not _FFPROBE_AVAILABLE:
        _warn_ffmpeg_missing()
        raise FfmpegNotAvailableError(
            "ffmpeg/ffprobe not found on PATH; install ffmpeg to process video/audio files"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = _run(
        [
            "ffmpeg",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-y",
            str(output_path),
        ]
    )
    if result.returncode != 0:
        logger.warning(
            "audio_extraction_failed", file=str(video_path), stderr=result.stderr.strip()
        )
        raise RuntimeError(f"ffmpeg failed to extract audio: {result.stderr.strip()}")

    metadata = _probe_metadata(video_path)
    logger.info(
        "audio_extracted",
        file=str(video_path),
        output=str(output_path),
        duration=metadata.duration_seconds,
    )
    return output_path, metadata


def _get_whisper_model(model_size: str) -> WhisperModel:
    if model_size not in _whisper_models:
        _whisper_models[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _whisper_models[model_size]


def transcribe_audio(audio_path: Path, *, model_size: str | None = None) -> TranscriptionResult:
    """Transcribe audio_path into timestamped segments via faster-whisper.

    Uses settings.whisper_model_size (default base) unless model_size is
    given. Runs on CPU with int8 quantization, matching the configuration
    validated in spikes/faster_whisper_test.py.
    """
    model = _get_whisper_model(model_size or settings.whisper_model_size)
    segments_iter, info = model.transcribe(str(audio_path), beam_size=5)
    segments = [
        TranscriptSegment(start=seg.start, end=seg.end, text=seg.text.strip())
        for seg in segments_iter
    ]
    logger.info(
        "audio_transcribed",
        file=str(audio_path),
        segment_count=len(segments),
        language=info.language,
    )
    return TranscriptionResult(
        segments=segments,
        language=info.language,
        language_probability=info.language_probability,
    )


def format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def generate_transcript_markdown(segments: list[TranscriptSegment], video_filename: str) -> str:
    """Render timestamped segments into a markdown transcript with a YAML
    frontmatter block and one hypatia://open deep-link header per segment,
    so the frontend can jump the player to that time.
    """
    duration = segments[-1].end if segments else 0.0
    lines = [
        "---",
        f"source: {video_filename}",
        "type: transcript",
        f"duration: {format_timestamp(duration)}",
        "---",
        "",
        f"# Transcript: {video_filename}",
        "",
    ]
    for segment in segments:
        start_ts = format_timestamp(segment.start)
        end_ts = format_timestamp(segment.end)
        lines.append(
            f"## [{start_ts} - {end_ts}]"
            f"(hypatia://open?file={quote(video_filename)}&t={int(segment.start)})"
        )
        lines.append(segment.text)
        lines.append("")
    return "\n".join(lines)


async def update_file_status(
    session: AsyncSession,
    file_id: UUID,
    status: FileStatus,
    *,
    converted_path: str | None = None,
    error_message: str | None = None,
) -> None:
    file_ = await session.get(File, file_id)
    if file_ is None:
        logger.warning("file_not_found_for_status_update", file_id=str(file_id))
        return
    file_.status = status
    if converted_path is not None:
        file_.converted_path = converted_path
    if error_message is not None:
        file_.error_message = error_message
    await session.commit()


async def process_video(
    session: AsyncSession,
    file_id: UUID,
    file_path: Path,
    output_path: Path,
) -> ProcessingResult:
    """Orchestrate the full video/audio -> transcript pipeline for one File.

    1. Extract audio (ffmpeg) -> WAV + video metadata.
    2. Transcribe (faster-whisper) -> timestamped segments.
    3. Render + write the markdown transcript and its metadata sidecar.
    4. Delete the intermediate WAV.
    5. Update the File row status to ready (with converted_path) or error
       (with error_message).

    Never raises: pipeline failures are caught, recorded on the File row,
    and reflected in the returned ProcessingResult.
    """
    tmp_wav = output_path.with_suffix(".wav")
    metadata: dict[str, Any] = {}
    try:
        _, video_metadata = await asyncio.to_thread(extract_audio, file_path, tmp_wav)
        transcription = await asyncio.to_thread(transcribe_audio, tmp_wav)
        markdown = generate_transcript_markdown(transcription.segments, file_path.name)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")

        metadata = {
            "source_filename": file_path.name,
            "duration_seconds": video_metadata.duration_seconds,
            "segment_count": len(transcription.segments),
            "model": settings.whisper_model_size,
            "language": transcription.language,
            "width": video_metadata.width,
            "height": video_metadata.height,
            "codec": video_metadata.codec,
            "frame_rate": video_metadata.frame_rate,
        }
        metadata_path = output_path.with_suffix(".metadata.json")
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        # Deferred import: summary_generator imports from this module, so a
        # top-level import here would be circular.
        from app.services.summary_generator import generate_transcript_summary, summary_path_for

        summary_text = generate_transcript_summary(
            transcription.segments, file_path.name, video_metadata.duration_seconds
        )
        summary_path_for(output_path).write_text(summary_text, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 -- pipeline failures are recorded, not raised
        error = str(exc)
        logger.warning("video_processing_failed", file=str(file_path), error=error)
        tmp_wav.unlink(missing_ok=True)
        await update_file_status(session, file_id, FileStatus.ERROR, error_message=error)
        return ProcessingResult(success=False, error=error)

    tmp_wav.unlink(missing_ok=True)
    await update_file_status(session, file_id, FileStatus.READY, converted_path=str(output_path))
    logger.info("video_processed", file=str(file_path), output=str(output_path))
    return ProcessingResult(success=True, converted_path=output_path, metadata=metadata)
