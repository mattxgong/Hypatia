"""Tests for the citation service (Task 3A.3)."""

from __future__ import annotations

import pytest

from app.services.citation_service import CitationRef, generate_citation_uri, parse_citation_uri


def test_generate_pdf_citation():
    uri = generate_citation_uri("chapter-3.pdf", "page", "5")
    assert uri == "hypatia://cite?file=chapter-3.pdf&page=5"


def test_generate_video_citation():
    uri = generate_citation_uri("lecture-1.mp4", "t", "342")
    assert uri == "hypatia://cite?file=lecture-1.mp4&t=342"


def test_generate_section_citation():
    uri = generate_citation_uri("notes.md", "section", "introduction")
    assert uri == "hypatia://cite?file=notes.md&section=introduction"


def test_generate_line_citation():
    uri = generate_citation_uri("code.py", "line", "42")
    assert uri == "hypatia://cite?file=code.py&line=42"


def test_generate_file_only():
    uri = generate_citation_uri("notes.md")
    assert uri == "hypatia://cite?file=notes.md"


def test_generate_invalid_location_type():
    with pytest.raises(ValueError, match="Invalid location_type"):
        generate_citation_uri("f.pdf", "invalid", "1")


def test_parse_pdf_citation():
    ref = parse_citation_uri("hypatia://cite?file=chapter-3.pdf&page=5")
    assert ref == CitationRef(file_id="chapter-3.pdf", location_type="page", location_value="5")


def test_parse_video_citation():
    ref = parse_citation_uri("hypatia://cite?file=lecture.mp4&t=342")
    assert ref == CitationRef(file_id="lecture.mp4", location_type="t", location_value="342")


def test_parse_file_only():
    ref = parse_citation_uri("hypatia://cite?file=notes.md")
    assert ref == CitationRef(file_id="notes.md", location_type=None, location_value=None)


def test_parse_invalid_scheme():
    assert parse_citation_uri("https://example.com") is None


def test_parse_invalid_host():
    assert parse_citation_uri("hypatia://other?file=x") is None


def test_parse_no_file_param():
    assert parse_citation_uri("hypatia://cite?page=5") is None


def test_roundtrip():
    uri = generate_citation_uri("doc.pdf", "page", "12")
    ref = parse_citation_uri(uri)
    assert ref is not None
    assert ref.file_id == "doc.pdf"
    assert ref.location_type == "page"
    assert ref.location_value == "12"
