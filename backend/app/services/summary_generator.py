"""Source summary generation (Task 2.8).

Produces a short, heuristic digest -- no LLM calls here, that's Phase 3's
wiki engine -- alongside each converted file, written to
``converted/{stem}.summary.md``. This is what the wiki engine will read as
its source-summary input:

- Documents: leading paragraphs + headings + a metadata block.
- Video/audio transcripts: duration + a handful of evenly-spaced,
  timestamped excerpts standing in for "key timestamps".
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.services.video_processor import TranscriptSegment, format_timestamp

_MAX_SUMMARY_PARAGRAPHS = 3
_MAX_KEY_TIMESTAMPS = 5

_HEADING_RE = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)


def summary_path_for(output_path: Path) -> Path:
    """Return the ``{stem}.summary.md`` path alongside a converted output."""
    return output_path.with_name(f"{output_path.stem}.summary.md")


def generate_document_summary(
    markdown_text: str, metadata: dict[str, Any], source_filename: str
) -> str:
    """Summarize a converted document: leading paragraphs, headings, metadata."""
    headings = _HEADING_RE.findall(markdown_text)
    paragraphs = [
        p.strip()
        for p in markdown_text.split("\n\n")
        if p.strip() and not p.strip().startswith("#")
    ]
    excerpt = "\n\n".join(paragraphs[:_MAX_SUMMARY_PARAGRAPHS])

    lines = [
        "---",
        f"source: {source_filename}",
        "type: source-summary",
        f"word_count: {metadata.get('word_count', 0)}",
        "---",
        "",
        f"# Summary: {source_filename}",
        "",
    ]
    if headings:
        lines.append("## Headings")
        lines.append("")
        lines.extend(headings)
        lines.append("")
    if excerpt:
        lines.append("## Excerpt")
        lines.append("")
        lines.append(excerpt)
        lines.append("")
    return "\n".join(lines)


def _pick_key_segments(segments: list[TranscriptSegment], count: int) -> list[TranscriptSegment]:
    if len(segments) <= count:
        return segments
    step = len(segments) / count
    return [segments[int(i * step)] for i in range(count)]


def generate_transcript_summary(
    segments: list[TranscriptSegment], video_filename: str, duration_seconds: float
) -> str:
    """Summarize a transcript: duration + a handful of key timestamps."""
    lines = [
        "---",
        f"source: {video_filename}",
        "type: source-summary",
        f"duration: {format_timestamp(duration_seconds)}",
        "---",
        "",
        f"# Summary: {video_filename}",
        "",
        "## Key timestamps",
        "",
    ]
    for segment in _pick_key_segments(segments, _MAX_KEY_TIMESTAMPS):
        ts = format_timestamp(segment.start)
        link = f"hypatia://open?file={quote(video_filename)}&t={int(segment.start)}"
        lines.append(f"- [{ts}]({link}) {segment.text}")
    lines.append("")
    return "\n".join(lines)
