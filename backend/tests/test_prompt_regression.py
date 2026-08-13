"""Prompt regression tests (Task 3B.10).

Tests structural correctness of LLM output parsing — not exact text matches.
Uses golden corpus in tests/golden/ with deterministic mock LLM outputs.
Asserts: frontmatter present, citations valid, cross-references resolve,
page categories correct, page paths valid.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.wiki_parser import ParsedWikiPage, parse_llm_output

GOLDEN_DIR = Path(__file__).parent / "golden"
SOURCES_DIR = GOLDEN_DIR / "sources"
EXPECTED_DIR = GOLDEN_DIR / "expected"

VALID_CATEGORIES = {"source-summary", "concept", "entity", "synthesis"}
CITATION_PATTERN = re.compile(r"hypatia://cite\?file=([^&\"]+)(&[^)\"]+)?")
WIKI_LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")
PATH_PATTERN = re.compile(r"^pages/[a-z-]+/[a-z0-9-]+\.md$")


def _load_golden_outputs() -> list[tuple[str, str]]:
    """Load all golden expected output files. Returns (name, raw_content) pairs."""
    results = []
    for f in sorted(EXPECTED_DIR.glob("*.xml")):
        results.append((f.stem, f.read_text(encoding="utf-8")))
    return results


def _validate_frontmatter(page: ParsedWikiPage) -> list[str]:
    """Validate frontmatter fields. Returns list of issues."""
    issues: list[str] = []
    if not page.title:
        issues.append(f"Page {page.path}: missing title")
    if not page.category:
        issues.append(f"Page {page.path}: missing type/category")
    elif page.category not in VALID_CATEGORIES:
        issues.append(f"Page {page.path}: invalid category '{page.category}'")
    if page.sources is None:
        issues.append(f"Page {page.path}: missing sources field")
    return issues


def _validate_path(page: ParsedWikiPage) -> list[str]:
    """Validate page path format."""
    if not PATH_PATTERN.match(page.path):
        return [
            f"Page path '{page.path}' doesn't match expected pattern pages/<category>/<slug>.md"
        ]
    return []


def _validate_citations(page: ParsedWikiPage) -> list[str]:
    """Validate citation URIs are well-formed."""
    issues: list[str] = []
    for match in CITATION_PATTERN.finditer(page.content):
        filename = match.group(1)
        if not filename:
            issues.append(f"Page {page.path}: empty citation filename")
        if " " in filename:
            issues.append(f"Page {page.path}: citation filename contains spaces: '{filename}'")
    return issues


def _validate_wiki_links(pages: list[ParsedWikiPage]) -> list[str]:
    """Validate wiki links resolve to pages in the same output set."""
    slugs = {Path(p.path).stem for p in pages}
    issues: list[str] = []
    for page in pages:
        for match in WIKI_LINK_PATTERN.finditer(page.content):
            link_target = match.group(1)
            if link_target not in slugs:
                issues.append(
                    f"Page {page.path}: wiki link [[{link_target}]] "
                    f"doesn't resolve to any page in output"
                )
    return issues


class TestGoldenCorpusParsing:
    """Test that golden outputs parse correctly with the wiki parser."""

    @pytest.fixture(params=_load_golden_outputs(), ids=lambda x: x[0])
    def golden_output(self, request: pytest.FixtureRequest) -> tuple[str, str]:
        return request.param

    def test_parses_without_error(self, golden_output: tuple[str, str]):
        name, raw = golden_output
        pages = parse_llm_output(raw)
        assert len(pages) > 0, f"Golden {name}: no pages parsed"

    def test_produces_source_summary(self, golden_output: tuple[str, str]):
        name, raw = golden_output
        pages = parse_llm_output(raw)
        summaries = [p for p in pages if p.category == "source-summary"]
        assert len(summaries) >= 1, f"Golden {name}: no source-summary page found"

    def test_produces_concept_or_entity_pages(self, golden_output: tuple[str, str]):
        name, raw = golden_output
        pages = parse_llm_output(raw)
        non_summaries = [p for p in pages if p.category in ("concept", "entity")]
        assert len(non_summaries) >= 1, f"Golden {name}: no concept/entity pages found"

    def test_valid_frontmatter(self, golden_output: tuple[str, str]):
        name, raw = golden_output
        pages = parse_llm_output(raw)
        all_issues: list[str] = []
        for page in pages:
            all_issues.extend(_validate_frontmatter(page))
        assert not all_issues, f"Golden {name} frontmatter issues:\n" + "\n".join(all_issues)

    def test_valid_paths(self, golden_output: tuple[str, str]):
        name, raw = golden_output
        pages = parse_llm_output(raw)
        all_issues: list[str] = []
        for page in pages:
            all_issues.extend(_validate_path(page))
        assert not all_issues, f"Golden {name} path issues:\n" + "\n".join(all_issues)

    def test_citations_wellformed(self, golden_output: tuple[str, str]):
        name, raw = golden_output
        pages = parse_llm_output(raw)
        all_issues: list[str] = []
        for page in pages:
            all_issues.extend(_validate_citations(page))
        assert not all_issues, f"Golden {name} citation issues:\n" + "\n".join(all_issues)

    def test_has_citations(self, golden_output: tuple[str, str]):
        name, raw = golden_output
        pages = parse_llm_output(raw)
        total_citations = sum(len(CITATION_PATTERN.findall(p.content)) for p in pages)
        assert total_citations >= 1, f"Golden {name}: no citations found in any page"

    def test_wiki_links_resolve(self, golden_output: tuple[str, str]):
        name, raw = golden_output
        pages = parse_llm_output(raw)
        issues = _validate_wiki_links(pages)
        assert not issues, f"Golden {name} link issues:\n" + "\n".join(issues)

    def test_has_tags(self, golden_output: tuple[str, str]):
        name, raw = golden_output
        pages = parse_llm_output(raw)
        pages_without_tags = [p for p in pages if not p.tags]
        assert not pages_without_tags, f"Golden {name}: pages missing tags: " + ", ".join(
            p.path for p in pages_without_tags
        )


class TestStructuralProperties:
    """Test structural properties that should hold for any valid LLM output."""

    def test_page_count_range(self):
        """Each source should produce 2-8 pages (1 summary + concepts/entities)."""
        for f in EXPECTED_DIR.glob("*.xml"):
            raw = f.read_text(encoding="utf-8")
            pages = parse_llm_output(raw)
            assert 2 <= len(pages) <= 8, f"{f.stem}: expected 2-8 pages, got {len(pages)}"

    def test_no_duplicate_paths(self):
        """No two pages in the same output should have the same path."""
        for f in EXPECTED_DIR.glob("*.xml"):
            raw = f.read_text(encoding="utf-8")
            pages = parse_llm_output(raw)
            paths = [p.path for p in pages]
            assert len(paths) == len(set(paths)), (
                f"{f.stem}: duplicate paths found: {[p for p in paths if paths.count(p) > 1]}"
            )

    def test_source_summary_references_source_id(self):
        """Source summary pages should have at least one source ID."""
        for f in EXPECTED_DIR.glob("*.xml"):
            raw = f.read_text(encoding="utf-8")
            pages = parse_llm_output(raw)
            for page in pages:
                if page.category == "source-summary":
                    assert page.sources, (
                        f"{f.stem}: source-summary '{page.path}' has empty sources list"
                    )

    def test_content_not_empty(self):
        """Every page should have non-trivial content."""
        for f in EXPECTED_DIR.glob("*.xml"):
            raw = f.read_text(encoding="utf-8")
            pages = parse_llm_output(raw)
            for page in pages:
                assert len(page.content.strip()) > 50, (
                    f"{f.stem}: page '{page.path}' has very short content ({len(page.content)} chars)"
                )

    def test_categories_are_consistent_with_paths(self):
        """Page type should match the directory in the path."""
        category_to_dir = {
            "source-summary": "source-summaries",
            "concept": "concepts",
            "entity": "entities",
            "synthesis": "synthesis",
        }
        for f in EXPECTED_DIR.glob("*.xml"):
            raw = f.read_text(encoding="utf-8")
            pages = parse_llm_output(raw)
            for page in pages:
                if page.category in category_to_dir:
                    expected_dir = category_to_dir[page.category]
                    parts = page.path.split("/")
                    if len(parts) >= 3:
                        actual_dir = parts[1]
                        assert actual_dir == expected_dir, (
                            f"{f.stem}: page '{page.path}' has type '{page.category}' "
                            f"but is in directory '{actual_dir}' (expected '{expected_dir}')"
                        )
