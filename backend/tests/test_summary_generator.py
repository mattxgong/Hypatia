"""Task 2.8 acceptance: source summary generation."""

from __future__ import annotations

from pathlib import Path

from app.services import summary_generator
from app.services.video_processor import TranscriptSegment


def test_summary_path_for() -> None:
    output = Path("/data/converted/notes.md")
    assert summary_generator.summary_path_for(output) == Path("/data/converted/notes.summary.md")


def test_generate_document_summary_includes_headings_and_excerpt() -> None:
    markdown_text = (
        "# Lecture 1\n\n"
        "This is the first paragraph of real content.\n\n"
        "## Background\n\n"
        "This is the second paragraph.\n\n"
        "This is the third paragraph.\n\n"
        "This is a fourth paragraph that should be excluded from the excerpt.\n"
    )
    metadata = {"word_count": 42}

    summary = summary_generator.generate_document_summary(markdown_text, metadata, "lecture1.pdf")

    assert "source: lecture1.pdf" in summary
    assert "type: source-summary" in summary
    assert "word_count: 42" in summary
    assert "# Lecture 1" in summary
    assert "## Background" in summary
    assert "This is the first paragraph of real content." in summary
    assert "This is the third paragraph." in summary
    assert "fourth paragraph" not in summary


def test_generate_document_summary_handles_no_headings_or_paragraphs() -> None:
    summary = summary_generator.generate_document_summary("", {}, "empty.txt")

    assert "source: empty.txt" in summary
    assert "word_count: 0" in summary
    assert "## Headings" not in summary
    assert "## Excerpt" not in summary


def test_generate_transcript_summary_includes_duration_and_timestamps() -> None:
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="Welcome to the lecture."),
        TranscriptSegment(start=5.0, end=12.5, text="Today we cover Fourier transforms."),
    ]

    summary = summary_generator.generate_transcript_summary(segments, "lecture-1.mp4", 12.5)

    assert "source: lecture-1.mp4" in summary
    assert "type: source-summary" in summary
    assert "duration: 00:00:12" in summary
    assert "## Key timestamps" in summary
    assert "hypatia://open?file=lecture-1.mp4&t=0" in summary
    assert "Welcome to the lecture." in summary
    assert "hypatia://open?file=lecture-1.mp4&t=5" in summary


def test_generate_transcript_summary_handles_no_segments() -> None:
    summary = summary_generator.generate_transcript_summary([], "silence.mp4", 0.0)

    assert "duration: 00:00:00" in summary
    assert "## Key timestamps" in summary


def test_generate_transcript_summary_caps_key_timestamps() -> None:
    segments = [
        TranscriptSegment(start=float(i), end=float(i + 1), text=f"segment {i}") for i in range(20)
    ]

    summary = summary_generator.generate_transcript_summary(segments, "long.mp4", 20.0)

    assert summary.count("hypatia://open") == summary_generator._MAX_KEY_TIMESTAMPS
