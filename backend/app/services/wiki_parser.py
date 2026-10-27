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

_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def is_git_path_part(part: str) -> bool:
    """True for ``.git`` and the spellings Windows resolves to it (``.GIT``, ``.git.``)."""
    return part.rstrip(". ").casefold() == ".git"


def normalize_page_path(path: str, *, require_pages_dir: bool = True) -> str | None:
    """Return ``path`` as a safe wiki-relative ``*.md`` path, or None if it could escape the wiki.

    Page paths come from LLM output, API requests and backups, and are joined
    onto the wiki directory, so anything absolute, with ``..``/``.git`` parts,
    or (with ``require_pages_dir``) outside ``pages/`` is rejected.
    """
    candidate = path.strip().replace("\\", "/")
    while candidate.startswith("./"):
        candidate = candidate[2:]
    if not candidate or candidate.startswith("/") or _DRIVE_RE.match(candidate):
        return None
    parts = candidate.split("/")
    if any(part in {"", ".", ".."} or ":" in part or is_git_path_part(part) for part in parts):
        return None
    if not candidate.lower().endswith(".md"):
        return None
    if require_pages_dir and (len(parts) < 2 or parts[0] != "pages"):
        return None
    return candidate


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
    for raw_path, action, body in matches:
        path = normalize_page_path(raw_path)
        if path is None:
            logger.warning("wiki_parse_unsafe_path", path=raw_path)
            continue
        page = _parse_single_page(path, action or "create", body.strip())
        if page is None:
            continue
        pages.append(page)

    return pages


def parse_page_document(path: str, document: str) -> ParsedWikiPage | None:
    """Parse a stored page (frontmatter + body), e.g. one read back from git."""
    return _parse_single_page(path, "update", document.strip())


def page_body(document: str) -> str:
    """A stored page's markdown without its frontmatter."""
    match = _FRONTMATTER_PATTERN.match(document.lstrip())
    return match.group(2).strip() if match else document.strip()


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
