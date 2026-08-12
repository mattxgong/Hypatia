"""Parse LLM-generated wiki pages from XML-tagged output.

Ported from the validated spike at ``spikes/llm_parsing_test.py`` with
extensions for the ``action`` attribute and full frontmatter extraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from app.models.db_models import WikiCategory
from app.utils.logging import get_logger

logger = get_logger()

_PAGE_PATTERN = re.compile(
    r'<wiki-page\s+path="([^"]+)"(?:\s+action="([^"]+)")?>\s*(.*?)\s*</wiki-page>',
    re.DOTALL,
)

_FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n(.*)$",
    re.DOTALL,
)

_VALID_CATEGORIES = {c.value for c in WikiCategory}


@dataclass
class ParsedWikiPage:
    """A single wiki page extracted from LLM output."""

    path: str
    action: str = "create"
    title: str = ""
    category: str = "concept"
    sources: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    content: str = ""
    user_edited: bool = False
    raw_frontmatter: str = ""


def parse_llm_output(raw: str) -> list[ParsedWikiPage]:
    """Extract wiki pages from LLM XML-tagged output.

    Skips pages that fail validation (missing title) and logs warnings.
    Returns an empty list if no valid pages are found.
    """
    matches = _PAGE_PATTERN.findall(raw)
    if not matches:
        logger.warning("wiki_parse_no_pages", output_length=len(raw))
        return []

    pages: list[ParsedWikiPage] = []
    for path, action, body in matches:
        page = _parse_single_page(path, action or "create", body.strip())
        if page is None:
            continue
        pages.append(page)

    return pages


def _parse_single_page(path: str, action: str, body: str) -> ParsedWikiPage | None:
    """Parse a single page body (frontmatter + content). Returns None on failure."""
    fm_match = _FRONTMATTER_PATTERN.match(body)
    if not fm_match:
        logger.warning("wiki_parse_no_frontmatter", path=path)
        return None

    frontmatter_str = fm_match.group(1)
    content = fm_match.group(2).strip()

    try:
        fm = yaml.safe_load(frontmatter_str)
    except yaml.YAMLError:
        logger.warning("wiki_parse_yaml_error", path=path)
        return None

    if not isinstance(fm, dict):
        logger.warning("wiki_parse_invalid_frontmatter", path=path)
        return None

    title = str(fm.get("title", "")).strip()
    if not title:
        logger.warning("wiki_parse_missing_title", path=path)
        return None

    raw_category = str(fm.get("type", "concept")).strip()
    category = raw_category if raw_category in _VALID_CATEGORIES else "concept"
    if raw_category not in _VALID_CATEGORIES and raw_category != "concept":
        logger.warning("wiki_parse_invalid_category", path=path, category=raw_category)

    sources_raw = fm.get("sources", [])
    sources = [str(s) for s in sources_raw] if isinstance(sources_raw, list) else []

    tags_raw = fm.get("tags", [])
    tags = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []

    user_edited = bool(fm.get("user_edited", False))

    return ParsedWikiPage(
        path=path,
        action=action,
        title=title,
        category=category,
        sources=sources,
        tags=tags,
        content=content,
        user_edited=user_edited,
        raw_frontmatter=frontmatter_str,
    )
