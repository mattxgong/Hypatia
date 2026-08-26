"""Core wiki engine: all commands (Phase 3A + 3B).

Orchestrates the LLM wiki pattern: reads converted source material, prompts
the LLM to generate wiki pages, parses output, writes pages to disk and DB,
and answers user queries from the wiki. Also provides wiki page CRUD, export,
index/log management, and commands: /summarize, /remove, /lint, /rebuild.
"""

from __future__ import annotations

import json
import re
import uuid
import zipfile
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import tiktoken
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.db_models import (
    ChatMessage,
    ChatRole,
    File,
    FileStatus,
    WikiCategory,
    WikiPage,
)
from app.services.llm_service import get_llm_provider
from app.services.prompts.ingest_prompt import INGEST_SYSTEM_PROMPT
from app.services.prompts.lint_prompt import LINT_SYSTEM_PROMPT
from app.services.prompts.query_prompt import ASK_SYSTEM_PROMPT
from app.services.prompts.summarize_prompt import SUMMARIZE_SYSTEM_PROMPT
from app.services.prompts.wiki_schema import WIKI_SCHEMA
from app.services.wiki_git import commit_wiki_change, init_wiki_repo, wiki_dir
from app.services.wiki_parser import ParsedWikiPage, parse_llm_output
from app.services.wiki_search import (
    delete_fts_page,
    hybrid_search,
    sync_fts_page,
)
from app.utils.logging import get_logger

logger = get_logger()


async def _upsert_embedding_safe(
    session: AsyncSession, page_id: uuid.UUID | str, content: str
) -> None:
    """Upsert embedding, silently skipping if unavailable or table missing."""
    try:
        from app.services.embedding_service import upsert_embedding

        async with session.begin_nested():
            await upsert_embedding(session, page_id, content)
    except ImportError:
        pass
    except Exception:  # noqa: BLE001
        logger.debug("embedding_upsert_skipped", page_id=str(page_id))


async def _delete_embedding_safe(session: AsyncSession, page_id: uuid.UUID | str) -> None:
    """Delete embedding, silently skipping if unavailable or table missing."""
    try:
        from app.services.embedding_service import delete_embedding

        async with session.begin_nested():
            await delete_embedding(session, page_id)
    except ImportError:
        pass
    except Exception:  # noqa: BLE001
        logger.debug("embedding_delete_skipped", page_id=str(page_id))


_ENCODER: tiktoken.Encoding | None = None

# Assumes the largest common context window across supported models.
# Individual providers may differ; revisit if smaller-context models are added.
_DEFAULT_CONTEXT_WINDOW = 128_000


def _get_encoder() -> tiktoken.Encoding:
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return _ENCODER


def _count_tokens(text: str) -> int:
    return len(_get_encoder().encode(text))


@dataclass
class IngestResult:
    """Result of ingesting a source file into the wiki."""

    success: bool
    pages_created: list[str] = field(default_factory=list)
    pages_updated: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class AskResult:
    """Result of an /ask query."""

    answer: str
    pages_consulted: list[str] = field(default_factory=list)


@dataclass
class WikiTreeNode:
    """A node in the wiki page tree (for sidebar display)."""

    path: str
    title: str
    category: str
    user_edited: bool


@dataclass
class WikiPageContent:
    """Full content of a wiki page (for page view)."""

    path: str
    title: str
    category: str
    content: str
    user_edited: bool
    source_file_ids: list[str]


@dataclass
class ExportResult:
    """Result of a /export operation."""

    success: bool
    export_path: str | None = None
    page_count: int = 0
    error: str | None = None


@dataclass
class SummarizeResult:
    """Result of a /summarize operation."""

    success: bool
    page_path: str | None = None
    error: str | None = None


@dataclass
class RemoveResult:
    """Result of a /remove operation."""

    success: bool
    pages_deleted: list[str] = field(default_factory=list)
    pages_updated: list[str] = field(default_factory=list)
    dead_links_cleaned: int = 0
    error: str | None = None


@dataclass
class LintIssue:
    """A single wiki lint issue."""

    severity: str
    issue_type: str
    page: str
    description: str
    suggestion: str = ""


@dataclass
class LintResult:
    """Result of a /lint operation."""

    success: bool
    issues: list[LintIssue] = field(default_factory=list)
    error: str | None = None


@dataclass
class RebuildPreview:
    """Preview of what /rebuild would do (dry-run)."""

    pages_to_create: list[str]
    pages_to_delete: list[str]
    pages_preserved_user_edited: list[str]
    source_file_count: int
    estimated_tokens: int


@dataclass
class RebuildResult:
    """Result of a /rebuild operation."""

    success: bool
    pages_created: int = 0
    pages_deleted: int = 0
    pages_preserved: int = 0
    error: str | None = None


async def ingest_source(
    session: AsyncSession,
    class_id: uuid.UUID,
    file_id: uuid.UUID,
) -> IngestResult:
    """Ingest a converted source file into the wiki.

    Reads the full converted markdown, prompts the LLM to generate wiki pages,
    writes them to disk and database, and commits via git.
    """
    cid = str(class_id)

    file_record = await session.get(File, file_id)
    if file_record is None:
        return IngestResult(success=False, error="File not found")
    if file_record.status != FileStatus.READY:
        return IngestResult(success=False, error=f"File status is {file_record.status.value}")
    if not file_record.converted_path:
        return IngestResult(success=False, error="No converted file available")

    converted_path = Path(file_record.converted_path)
    if not converted_path.exists():
        return IngestResult(success=False, error=f"Converted file missing: {converted_path}")

    source_content = converted_path.read_text(encoding="utf-8")
    source_tokens = _count_tokens(source_content)

    # Cache token count for fast rebuild-preview estimates
    metadata = file_record.metadata_json or {}
    if metadata.get("token_count") != source_tokens:
        metadata["token_count"] = source_tokens
        file_record.metadata_json = metadata

    source_budget = int(_DEFAULT_CONTEXT_WINDOW * 0.50)

    if source_tokens > source_budget:
        chunks = _chunk_source(source_content, source_budget)
    else:
        chunks = [source_content]

    wiki_path = init_wiki_repo(cid)
    index_content = _read_index(wiki_path)
    existing_pages_context = await _get_related_pages_context(
        session, class_id, source_content[:500]
    )

    result = IngestResult(success=True)
    filename = file_record.original_filename
    provider = get_llm_provider()

    for i, chunk in enumerate(chunks):
        user_prompt = _build_ingest_prompt(
            chunk, filename, str(file_id), index_content, existing_pages_context, i, len(chunks)
        )

        try:
            raw_output = await provider.complete(
                INGEST_SYSTEM_PROMPT, user_prompt, max_tokens=settings.llm_max_tokens
            )
        except (OSError, ValueError, RuntimeError) as e:
            logger.error("ingest_llm_error", class_id=cid, file_id=str(file_id), error=str(e))
            result.success = False
            result.error = f"LLM error: {e}"
            return result

        pages = parse_llm_output(raw_output)
        if not pages:
            logger.warning("ingest_no_pages_parsed", class_id=cid, file_id=str(file_id), chunk=i)
            if len(chunks) == 1:
                result.success = False
                result.error = "LLM produced no parseable wiki pages"
                return result
            continue

        for page in pages:
            await _write_wiki_page(session, class_id, file_id, page, wiki_path)
            if page.action == "update":
                result.pages_updated.append(page.path)
            else:
                result.pages_created.append(page.path)

        index_content = _rebuild_index_from_disk(wiki_path)

    _write_index(wiki_path, index_content)
    _append_log(wiki_path, "ingest", filename, result)
    await session.commit()

    commit_wiki_change(cid, f"ingest: {filename}")
    logger.info(
        "ingest_complete",
        class_id=cid,
        file_id=str(file_id),
        created=len(result.pages_created),
        updated=len(result.pages_updated),
    )
    return result


async def handle_ask(
    session: AsyncSession,
    class_id: uuid.UUID,
    query: str,
) -> AskResult:
    """Answer a user question by searching the wiki and prompting the LLM."""
    cid = str(class_id)

    search_results = await hybrid_search(session, class_id, query, limit=10)

    wiki_path = wiki_dir(cid)
    pages_context: list[str] = []
    pages_consulted: list[str] = []
    token_budget = 90_000

    index_path = wiki_path / "index.md"
    if index_path.exists():
        index_text = index_path.read_text(encoding="utf-8")
        pages_context.append(f"## Wiki Index\n\n{index_text}")
        token_budget -= _count_tokens(index_text)

    for sr in search_results:
        page_file = wiki_path / sr.path
        if not page_file.exists():
            continue
        page_content = page_file.read_text(encoding="utf-8")
        page_tokens = _count_tokens(page_content)
        if page_tokens > token_budget:
            break
        pages_context.append(f"## Page: {sr.title}\nPath: {sr.path}\n\n{page_content}")
        pages_consulted.append(sr.path)
        token_budget -= page_tokens

    if not pages_consulted:
        answer = "I don't have any wiki pages yet to answer your question. Try uploading some source material first."
        await _save_chat_messages(session, class_id, query, answer, "ask")
        return AskResult(answer=answer, pages_consulted=[])

    separator = "---\n"
    context_block = separator.join(pages_context)
    user_prompt = f"## Context\n\n{context_block}\n\n---\n\n## Question\n\n{query}"

    try:
        provider = get_llm_provider()
        answer = await provider.complete(
            ASK_SYSTEM_PROMPT, user_prompt, max_tokens=settings.llm_max_tokens
        )
    except (OSError, ValueError, RuntimeError) as e:
        logger.error("ask_llm_error", class_id=cid, error=str(e))
        answer = f"Error generating answer: {e}"

    await _save_chat_messages(session, class_id, query, answer, "ask")
    return AskResult(answer=answer, pages_consulted=pages_consulted)


def _chunk_source(content: str, token_budget: int) -> list[str]:
    """Split source content into chunks that fit within the token budget."""
    encoder = _get_encoder()
    lines = content.split("\n")
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_tokens = 0

    for line in lines:
        line_tokens = len(encoder.encode(line + "\n"))
        if current_tokens + line_tokens > token_budget and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_tokens = 0
        current_chunk.append(line)
        current_tokens += line_tokens

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def _build_ingest_prompt(
    source_content: str,
    filename: str,
    file_id: str,
    index_content: str,
    existing_pages: str,
    chunk_index: int,
    total_chunks: int,
) -> str:
    parts = []
    if index_content:
        parts.append(f"## Current Wiki Index\n\n{index_content}")
    if existing_pages:
        parts.append(f"## Existing Related Pages\n\n{existing_pages}")

    chunk_note = ""
    if total_chunks > 1:
        chunk_note = (
            f"\n\nNote: This is chunk {chunk_index + 1} of {total_chunks}. "
            f"{'Create new pages for this content.' if chunk_index == 0 else 'Update existing pages created from earlier chunks, or create new ones as needed.'}"
        )

    parts.append(
        f"## Source Document\n\n"
        f"Filename: {filename}\n"
        f"File ID: {file_id}\n"
        f"{chunk_note}\n\n"
        f"---\n\n{source_content}"
    )
    return "\n\n".join(parts)


async def _get_related_pages_context(
    session: AsyncSession,
    class_id: uuid.UUID,
    query_hint: str,
) -> str:
    """Find existing related pages to include as context for the LLM."""
    budget = int(_DEFAULT_CONTEXT_WINDOW * 0.30)
    results = await hybrid_search(session, class_id, query_hint, limit=5)

    wiki_path = wiki_dir(str(class_id))
    pages_text: list[str] = []
    used_tokens = 0

    for sr in results:
        page_file = wiki_path / sr.path
        if not page_file.exists():
            continue
        content = page_file.read_text(encoding="utf-8")
        tokens = _count_tokens(content)
        if used_tokens + tokens > budget:
            break
        pages_text.append(f"### {sr.title} ({sr.path})\n\n{content}")
        used_tokens += tokens

    return "\n\n---\n\n".join(pages_text)


async def _write_wiki_page(
    session: AsyncSession,
    class_id: uuid.UUID,
    file_id: uuid.UUID,
    page: ParsedWikiPage,
    wiki_path: Path,
) -> None:
    """Write a parsed wiki page to disk and update the database + FTS index."""
    page_file = wiki_path / page.path

    if page_file.exists():
        existing_content = page_file.read_text(encoding="utf-8")
        if "user_edited: true" in existing_content[:500]:
            logger.info(
                "skip_user_edited_page",
                path=page.path,
                reason="user-edited page preserved during ingest",
            )
            return

    page_file.parent.mkdir(parents=True, exist_ok=True)

    full_content = _render_page_content(page, file_id)
    page_file.write_text(full_content, encoding="utf-8")

    category = WikiCategory(page.category)

    existing = await session.execute(
        select(WikiPage).where(WikiPage.class_id == class_id, WikiPage.path == page.path)
    )
    db_page = existing.scalar_one_or_none()

    if db_page is None:
        db_page = WikiPage(
            class_id=class_id,
            path=page.path,
            title=page.title,
            category=category,
            content=full_content,
            source_file_ids=page.sources or [str(file_id)],
        )
        session.add(db_page)
        await session.flush()
    else:
        db_page.title = page.title
        db_page.category = category
        db_page.content = full_content
        sources = list(set((db_page.source_file_ids or []) + (page.sources or [str(file_id)])))
        db_page.source_file_ids = sources
        db_page.updated_at = datetime.now(UTC)
        await session.flush()

    await sync_fts_page(
        session,
        page_id=db_page.id,
        class_id=class_id,
        path=page.path,
        title=page.title,
        content=page.content,
        tags=page.tags,
    )
    await _upsert_embedding_safe(session, db_page.id, page.content)


def _render_page_content(page: ParsedWikiPage, file_id: uuid.UUID) -> str:
    """Render a parsed page back into markdown with frontmatter."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    sources = page.sources or [str(file_id)]
    tags_str = ", ".join(page.tags) if page.tags else ""
    sources_str = ", ".join(sources)

    return (
        f"---\n"
        f'title: "{page.title}"\n'
        f"type: {page.category}\n"
        f"sources: [{sources_str}]\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f"tags: [{tags_str}]\n"
        f"user_edited: false\n"
        f"---\n\n"
        f"{page.content}\n"
    )


def _read_index(wiki_path: Path) -> str:
    """Read the current wiki index, or empty string if it doesn't exist."""
    index_file = wiki_path / "index.md"
    if index_file.exists():
        return index_file.read_text(encoding="utf-8")
    return ""


def _rebuild_index_from_disk(wiki_path: Path) -> str:
    """Scan wiki pages on disk and rebuild the index content."""
    pages_dir = wiki_path / "pages"
    if not pages_dir.exists():
        return ""

    sections: dict[str, list[str]] = {
        "source-summary": [],
        "concept": [],
        "entity": [],
        "synthesis": [],
    }

    _DIR_TO_CATEGORY = {
        "source-summaries": "source-summary",
        "concepts": "concept",
        "entities": "entity",
        "synthesis": "synthesis",
    }

    for md_file in sorted(pages_dir.rglob("*.md")):
        rel_path = md_file.relative_to(wiki_path)
        content = md_file.read_text(encoding="utf-8")
        title = _extract_title_from_content(content) or md_file.stem

        category = "concept"
        if len(rel_path.parts) > 1:
            dir_name = rel_path.parts[1]
            category = _DIR_TO_CATEGORY.get(dir_name, "concept")
        sections[category].append(f"- [{title}]({rel_path.as_posix()})")

    lines = ["# Wiki Index\n"]
    category_labels = {
        "source-summary": "Source Summaries",
        "concept": "Concepts",
        "entity": "Entities",
        "synthesis": "Synthesis",
    }
    for cat, label in category_labels.items():
        if sections[cat]:
            lines.append(f"\n## {label}\n")
            lines.extend(sections[cat])

    return "\n".join(lines) + "\n"


def _extract_title_from_content(content: str) -> str:
    """Extract title from YAML frontmatter."""
    for line in content.split("\n")[:10]:
        line = line.strip()
        if line.startswith("title:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


def _write_index(wiki_path: Path, content: str) -> None:
    """Write the index.md file."""
    index_file = wiki_path / "index.md"
    index_file.write_text(content, encoding="utf-8")


def _append_log(wiki_path: Path, action: str, detail: str, result: IngestResult) -> None:
    """Append an entry to log.md (legacy signature for ingest results)."""
    extra = ""
    if result.pages_created:
        extra += f"Created: {', '.join(result.pages_created)}\n"
    if result.pages_updated:
        extra += f"Updated: {', '.join(result.pages_updated)}\n"
    append_log(wiki_path, action, detail, extra)


def append_log(wiki_path: Path, action: str, detail: str, extra: str = "") -> None:
    """Append a timestamped entry to log.md (public, used by all commands)."""
    log_file = wiki_path / "log.md"
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    entry = f"\n## [{timestamp}] {action} | {detail}\n"
    if extra:
        entry += extra

    if log_file.exists():
        existing = log_file.read_text(encoding="utf-8")
        log_file.write_text(existing + entry, encoding="utf-8")
    else:
        log_file.write_text(f"# Wiki Log\n{entry}", encoding="utf-8")


async def _save_chat_messages(
    session: AsyncSession,
    class_id: uuid.UUID,
    query: str,
    answer: str,
    command: str,
) -> None:
    """Save the user query and assistant response to chat_messages."""
    user_msg = ChatMessage(
        class_id=class_id,
        role=ChatRole.USER,
        content=query,
        command=command,
    )
    assistant_msg = ChatMessage(
        class_id=class_id,
        role=ChatRole.ASSISTANT,
        content=answer,
        command=command,
    )
    session.add(user_msg)
    session.add(assistant_msg)
    await session.flush()


# ---------------------------------------------------------------------------
# Public API: CRUD, index/log, export (Tasks 3B.1, 3B.6, 3B.7)
# ---------------------------------------------------------------------------


async def get_wiki_tree(
    session: AsyncSession,
    class_id: uuid.UUID,
) -> list[WikiTreeNode]:
    """Return the wiki page tree for the sidebar."""
    result = await session.execute(
        select(WikiPage)
        .where(WikiPage.class_id == class_id)
        .order_by(WikiPage.category, WikiPage.title)
    )
    pages = result.scalars().all()
    nodes: list[WikiTreeNode] = []
    for page in pages:
        content = page.content or ""
        user_edited = "user_edited: true" in content[:500]
        nodes.append(
            WikiTreeNode(
                path=page.path,
                title=page.title,
                category=page.category.value,
                user_edited=user_edited,
            )
        )
    return nodes


async def get_wiki_page(
    session: AsyncSession,
    class_id: uuid.UUID,
    page_path: str,
) -> WikiPageContent | None:
    """Read a wiki page's full content from disk, with DB-authoritative source_file_ids."""
    wp = wiki_dir(str(class_id))
    page_file = wp / page_path
    if not page_file.exists():
        return None

    content = page_file.read_text(encoding="utf-8")
    title = _extract_title_from_content(content) or page_file.stem
    category = "concept"
    user_edited = False

    for line in content.split("\n")[:15]:
        stripped = line.strip()
        if stripped.startswith("type:"):
            category = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("user_edited:"):
            user_edited = "true" in stripped

    existing = await session.execute(
        select(WikiPage).where(WikiPage.class_id == class_id, WikiPage.path == page_path)
    )
    db_page = existing.scalar_one_or_none()
    source_file_ids = list(db_page.source_file_ids) if db_page and db_page.source_file_ids else []

    return WikiPageContent(
        path=page_path,
        title=title,
        category=category,
        content=content,
        user_edited=user_edited,
        source_file_ids=source_file_ids,
    )


def get_wiki_context(class_id: uuid.UUID) -> str:
    """Return the wiki schema + current index for LLM prompting."""
    wp = wiki_dir(str(class_id))
    index_content = _read_index(wp)
    parts = [WIKI_SCHEMA]
    if index_content:
        parts.append(f"\n\n## Current Wiki Index\n\n{index_content}")
    return "\n".join(parts)


async def update_wiki_page(
    session: AsyncSession,
    class_id: uuid.UUID,
    page_path: str,
    content: str,
    *,
    is_user_edit: bool = False,
) -> None:
    """Write updated content to a wiki page, update DB and FTS."""
    cid = str(class_id)
    wp = wiki_dir(cid)
    page_file = wp / page_path
    page_file.parent.mkdir(parents=True, exist_ok=True)

    if is_user_edit:
        content = _ensure_user_edited_flag(content)

    page_file.write_text(content, encoding="utf-8")

    title = _extract_title_from_content(content) or page_file.stem
    category_str = "concept"
    for line in content.split("\n")[:10]:
        if line.strip().startswith("type:"):
            category_str = line.strip().split(":", 1)[1].strip()
            break

    try:
        category = WikiCategory(category_str)
    except ValueError:
        category = WikiCategory.CONCEPT

    existing = await session.execute(
        select(WikiPage).where(WikiPage.class_id == class_id, WikiPage.path == page_path)
    )
    db_page = existing.scalar_one_or_none()

    if db_page is None:
        db_page = WikiPage(
            class_id=class_id,
            path=page_path,
            title=title,
            category=category,
            content=content,
            source_file_ids=[],
        )
        session.add(db_page)
        await session.flush()
    else:
        db_page.title = title
        db_page.category = category
        db_page.content = content
        db_page.updated_at = datetime.now(UTC)
        await session.flush()

    tags: list[str] = []
    for line in content.split("\n")[:15]:
        if line.strip().startswith("tags:"):
            raw = line.strip().split(":", 1)[1].strip().strip("[]")
            if raw:
                tags = [t.strip() for t in raw.split(",")]
            break

    await sync_fts_page(
        session,
        page_id=db_page.id,
        class_id=class_id,
        path=page_path,
        title=title,
        content=content,
        tags=tags,
    )
    await _upsert_embedding_safe(session, db_page.id, content)
    await session.commit()

    if is_user_edit:
        commit_wiki_change(cid, f"user-edit: modified {page_path}")


def _ensure_user_edited_flag(content: str) -> str:
    """Set user_edited: true in frontmatter, adding if missing."""
    if re.search(r"^user_edited:\s*true", content, re.MULTILINE):
        return content
    if re.search(r"^user_edited:\s*false", content, re.MULTILINE):
        return re.sub(
            r"^user_edited:\s*false", "user_edited: true", content, count=1, flags=re.MULTILINE
        )
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            return content[:end] + "user_edited: true\n" + content[end:]
    return content


async def rebuild_index(
    session: AsyncSession,
    class_id: uuid.UUID,
) -> str:
    """Rebuild index.md from wiki pages on disk, enriched with source counts."""
    cid = str(class_id)
    wp = wiki_dir(cid)
    pages_dir = wp / "pages"
    if not pages_dir.exists():
        _write_index(wp, "# Wiki Index\n")
        return "# Wiki Index\n"

    result = await session.execute(select(WikiPage).where(WikiPage.class_id == class_id))
    db_pages = {p.path: p for p in result.scalars().all()}

    sections: dict[str, list[str]] = {
        "source-summary": [],
        "concept": [],
        "entity": [],
        "synthesis": [],
    }
    _DIR_TO_CATEGORY = {
        "source-summaries": "source-summary",
        "concepts": "concept",
        "entities": "entity",
        "synthesis": "synthesis",
    }

    for md_file in sorted(pages_dir.rglob("*.md")):
        rel_path = md_file.relative_to(wp)
        rel_str = rel_path.as_posix()
        content = md_file.read_text(encoding="utf-8")
        title = _extract_title_from_content(content) or md_file.stem

        category = "concept"
        if len(rel_path.parts) > 1:
            dir_name = rel_path.parts[1]
            category = _DIR_TO_CATEGORY.get(dir_name, "concept")

        db_page = db_pages.get(rel_str)
        source_count = len(db_page.source_file_ids) if db_page and db_page.source_file_ids else 0
        suffix = (
            f" ({source_count} source{'s' if source_count != 1 else ''})" if source_count else ""
        )
        sections[category].append(f"- [{title}]({rel_str}){suffix}")

    lines = ["# Wiki Index\n"]
    category_labels = {
        "source-summary": "Source Summaries",
        "concept": "Concepts",
        "entity": "Entities",
        "synthesis": "Synthesis",
    }
    for cat, label in category_labels.items():
        if sections[cat]:
            lines.append(f"\n## {label}\n")
            lines.extend(sections[cat])

    index_content = "\n".join(lines) + "\n"
    _write_index(wp, index_content)
    return index_content


async def handle_export(
    session: AsyncSession,
    class_id: uuid.UUID,
    export_format: str = "zip",
) -> ExportResult:
    """Export the wiki as a ZIP archive."""
    cid = str(class_id)
    wp = wiki_dir(cid)
    pages_dir = wp / "pages"

    if not pages_dir.exists():
        return ExportResult(success=False, error="No wiki pages to export")

    md_files = list(pages_dir.rglob("*.md"))
    if not md_files:
        return ExportResult(success=False, error="No wiki pages to export")

    export_dir = settings.data_dir / "exports" / cid
    export_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    zip_path = export_dir / f"wiki_{timestamp}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        index_file = wp / "index.md"
        if index_file.exists():
            zf.write(index_file, "index.md")

        for md_file in sorted(md_files):
            arcname = md_file.relative_to(wp).as_posix()
            zf.write(md_file, arcname)

    page_count = len(md_files)
    append_log(wp, "export", f"{export_format} ({page_count} pages)")
    logger.info("wiki_exported", class_id=cid, page_count=page_count, path=str(zip_path))

    return ExportResult(
        success=True,
        export_path=str(zip_path),
        page_count=page_count,
    )


# ---------------------------------------------------------------------------
# Commands: /summarize, /remove, /lint, /rebuild (Tasks 3B.2-5)
# ---------------------------------------------------------------------------


async def handle_summarize(
    session: AsyncSession,
    class_id: uuid.UUID,
    topic: str,
) -> SummarizeResult:
    """Synthesize a summary page from wiki pages relevant to the topic."""
    cid = str(class_id)
    wp = wiki_dir(cid)

    search_results = await hybrid_search(session, class_id, topic, limit=10)
    if not search_results:
        return SummarizeResult(success=False, error="No wiki pages found for this topic")

    pages_context: list[str] = []
    token_budget = 80_000
    for sr in search_results:
        page_file = wp / sr.path
        if not page_file.exists():
            continue
        content = page_file.read_text(encoding="utf-8")
        tokens = _count_tokens(content)
        if tokens > token_budget:
            break
        pages_context.append(f"## Page: {sr.title}\nPath: {sr.path}\n\n{content}")
        token_budget -= tokens

    if not pages_context:
        return SummarizeResult(success=False, error="No readable pages found")

    context_block = "\n\n---\n\n".join(pages_context)
    user_prompt = f"## Topic to Summarize\n\n{topic}\n\n---\n\n## Source Pages\n\n{context_block}"

    try:
        provider = get_llm_provider()
        raw_output = await provider.complete(
            SUMMARIZE_SYSTEM_PROMPT, user_prompt, max_tokens=settings.llm_max_tokens
        )
    except (OSError, ValueError, RuntimeError) as e:
        logger.error("summarize_llm_error", class_id=cid, error=str(e))
        return SummarizeResult(success=False, error=f"LLM error: {e}")

    pages = parse_llm_output(raw_output)
    if not pages:
        return SummarizeResult(success=False, error="LLM produced no parseable output")

    page = pages[0]
    page_file = wp / page.path
    page_file.parent.mkdir(parents=True, exist_ok=True)
    full_content = _render_page_content(page, uuid.UUID(int=0))
    page_file.write_text(full_content, encoding="utf-8")

    category = WikiCategory.SYNTHESIS
    existing = await session.execute(
        select(WikiPage).where(WikiPage.class_id == class_id, WikiPage.path == page.path)
    )
    db_page = existing.scalar_one_or_none()

    if db_page is None:
        db_page = WikiPage(
            class_id=class_id,
            path=page.path,
            title=page.title,
            category=category,
            content=full_content,
            source_file_ids=page.sources or [],
        )
        session.add(db_page)
    else:
        db_page.title = page.title
        db_page.category = category
        db_page.content = full_content
        db_page.source_file_ids = page.sources or []
        db_page.updated_at = datetime.now(UTC)

    await session.flush()
    await sync_fts_page(
        session,
        page_id=db_page.id,
        class_id=class_id,
        path=page.path,
        title=page.title,
        content=page.content,
        tags=page.tags,
    )
    await _upsert_embedding_safe(session, db_page.id, page.content)

    index_content = _rebuild_index_from_disk(wp)
    _write_index(wp, index_content)
    append_log(wp, "summarize", topic, f"Created: {page.path}\n")
    await session.commit()
    commit_wiki_change(cid, f"summarize: {topic}")

    await _save_chat_messages(session, class_id, f"/summarize {topic}", page.path, "summarize")
    return SummarizeResult(success=True, page_path=page.path)


async def handle_remove(
    session: AsyncSession,
    class_id: uuid.UUID,
    filename: str,
) -> RemoveResult:
    """Remove a source file and clean up all associated wiki content."""
    cid = str(class_id)
    wp = wiki_dir(cid)

    result_q = await session.execute(
        select(File).where(
            File.class_id == class_id,
            File.original_filename == filename,
        )
    )
    file_record = result_q.scalar_one_or_none()
    if file_record is None:
        return RemoveResult(success=False, error=f"File not found: {filename}")

    file_id = str(file_record.id)

    if file_record.raw_path:
        raw = Path(file_record.raw_path)
        if raw.exists():
            raw.unlink()
    if file_record.converted_path:
        converted = Path(file_record.converted_path)
        if converted.exists():
            converted.unlink()
        summary_path = converted.with_suffix(".summary.md")
        if summary_path.exists():
            summary_path.unlink()

    result = RemoveResult(success=True)

    wiki_pages_q = await session.execute(select(WikiPage).where(WikiPage.class_id == class_id))
    all_pages = wiki_pages_q.scalars().all()

    for page in all_pages:
        sources = page.source_file_ids or []
        if file_id not in sources:
            continue

        if len(sources) == 1:
            page_file = wp / page.path
            if page_file.exists():
                page_file.unlink()
            await delete_fts_page(session, page.id)
            await _delete_embedding_safe(session, page.id)
            await session.delete(page)
            result.pages_deleted.append(page.path)
        else:
            new_sources = [s for s in sources if s != file_id]
            page.source_file_ids = new_sources
            page.updated_at = datetime.now(UTC)
            result.pages_updated.append(page.path)

    await session.delete(file_record)
    await session.flush()

    dead_links = _clean_dead_links(wp, result.pages_deleted)
    result.dead_links_cleaned = dead_links

    index_content = _rebuild_index_from_disk(wp)
    _write_index(wp, index_content)
    details = f"Deleted: {', '.join(result.pages_deleted)}\n" if result.pages_deleted else ""
    if result.pages_updated:
        details += f"Updated: {', '.join(result.pages_updated)}\n"
    if dead_links:
        details += f"Dead links cleaned: {dead_links}\n"
    append_log(wp, "remove", filename, details)
    await session.commit()
    commit_wiki_change(cid, f"remove: {filename}")

    logger.info(
        "remove_complete",
        class_id=cid,
        filename=filename,
        pages_deleted=len(result.pages_deleted),
        pages_updated=len(result.pages_updated),
    )
    return result


def _clean_dead_links(wiki_path: Path, deleted_paths: list[str]) -> int:
    """Remove [[wiki-links]] that point to deleted pages. Returns count of links cleaned."""
    if not deleted_paths:
        return 0

    deleted_slugs = {Path(p).stem for p in deleted_paths}
    pages_dir = wiki_path / "pages"
    if not pages_dir.exists():
        return 0

    cleaned = 0
    link_pattern = re.compile(r"\[\[([^\]]+)\]\]")

    def _replace_dead_link(m: re.Match[str]) -> str:
        nonlocal cleaned
        slug = m.group(1)
        if slug in deleted_slugs:
            cleaned += 1
            return slug
        return m.group(0)

    for md_file in pages_dir.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        new_content = link_pattern.sub(_replace_dead_link, content)
        if new_content != content:
            md_file.write_text(new_content, encoding="utf-8")

    return cleaned


async def handle_lint(
    session: AsyncSession,
    class_id: uuid.UUID,
) -> LintResult:
    """Audit the wiki for quality issues."""
    cid = str(class_id)
    wp = wiki_dir(cid)
    pages_dir = wp / "pages"

    if not pages_dir.exists():
        return LintResult(success=True, issues=[])

    issues: list[LintIssue] = []

    all_pages: dict[str, str] = {}
    all_slugs: set[str] = set()
    for md_file in pages_dir.rglob("*.md"):
        rel_path = md_file.relative_to(wp).as_posix()
        content = md_file.read_text(encoding="utf-8")
        all_pages[rel_path] = content
        all_slugs.add(md_file.stem)

    link_pattern = re.compile(r"\[\[([^\]]+)\]\]")
    cite_pattern = re.compile(r"hypatia://cite\?file=([^&\"]+)")
    inbound_links: dict[str, int] = {slug: 0 for slug in all_slugs}

    existing_files_q = await session.execute(
        select(File.original_filename).where(File.class_id == class_id)
    )
    existing_filenames = {row[0] for row in existing_files_q.fetchall()}

    for page_path, content in all_pages.items():
        for match in link_pattern.finditer(content):
            slug = match.group(1)
            if slug in inbound_links:
                inbound_links[slug] += 1
            elif slug not in all_slugs:
                issues.append(
                    LintIssue(
                        severity="warning",
                        issue_type="broken_link",
                        page=page_path,
                        description=f"Broken wiki link: [[{slug}]] — target page does not exist",
                        suggestion=f"Create page '{slug}' or remove the link",
                    )
                )

        for match in cite_pattern.finditer(content):
            cited_file = match.group(1)
            if cited_file not in existing_filenames:
                issues.append(
                    LintIssue(
                        severity="warning",
                        issue_type="dead_citation",
                        page=page_path,
                        description=f"Dead citation: references '{cited_file}' which no longer exists",
                        suggestion="Remove or update the citation",
                    )
                )

    for slug, count in inbound_links.items():
        if count == 0:
            page_paths = [p for p in all_pages if Path(p).stem == slug]
            if page_paths:
                path = page_paths[0]
                if "source-summaries" not in path:
                    issues.append(
                        LintIssue(
                            severity="suggestion",
                            issue_type="orphan_page",
                            page=path,
                            description=f"Orphan page: '{slug}' has no inbound wiki links",
                            suggestion="Add [[links]] from related pages or consider removing",
                        )
                    )

    if len(all_pages) >= 3:
        pages_for_llm: list[str] = []
        token_budget = 60_000
        for page_path, content in list(all_pages.items())[:20]:
            tokens = _count_tokens(content)
            if tokens > token_budget:
                break
            pages_for_llm.append(f"## {page_path}\n\n{content}")
            token_budget -= tokens

        if pages_for_llm:
            context = "\n\n---\n\n".join(pages_for_llm)
            user_prompt = f"## Wiki Pages to Audit\n\n{context}"
            try:
                provider = get_llm_provider()
                raw_output = await provider.complete(
                    LINT_SYSTEM_PROMPT, user_prompt, max_tokens=4096
                )
                for line in raw_output.strip().splitlines():
                    line = line.strip()
                    if not line or not line.startswith("{"):
                        continue
                    try:
                        obj = json.loads(line)
                        issues.append(
                            LintIssue(
                                severity=obj.get("severity", "suggestion"),
                                issue_type=obj.get("type", "quality"),
                                page=obj.get("page", ""),
                                description=obj.get("description", ""),
                                suggestion=obj.get("suggestion", ""),
                            )
                        )
                    except json.JSONDecodeError:
                        continue
            except (OSError, ValueError, RuntimeError) as e:
                logger.warning("lint_llm_error", class_id=cid, error=str(e))

    append_log(wp, "lint", f"{len(issues)} issues found")
    return LintResult(success=True, issues=issues)


async def handle_rebuild_preview(
    session: AsyncSession,
    class_id: uuid.UUID,
) -> RebuildPreview:
    """Dry-run /rebuild: calculate what would change without making changes."""
    cid = str(class_id)
    wp = wiki_dir(cid)
    pages_dir = wp / "pages"

    source_files_q = await session.execute(
        select(File).where(File.class_id == class_id, File.status == FileStatus.READY)
    )
    source_files = source_files_q.scalars().all()

    user_edited: list[str] = []
    to_delete: list[str] = []

    if pages_dir.exists():
        for md_file in pages_dir.rglob("*.md"):
            rel_path = md_file.relative_to(wp).as_posix()
            content = md_file.read_text(encoding="utf-8")
            if "user_edited: true" in content[:500]:
                user_edited.append(rel_path)
            else:
                to_delete.append(rel_path)

    estimated_tokens = 0
    for f in source_files:
        metadata = f.metadata_json or {}
        cached = metadata.get("token_count")
        if cached is not None:
            estimated_tokens += cached
        elif f.converted_path:
            p = Path(f.converted_path)
            if p.exists():
                estimated_tokens += _count_tokens(p.read_text(encoding="utf-8"))

    to_create = [
        f"pages/source-summaries/{Path(f.original_filename).stem}.md" for f in source_files
    ]

    return RebuildPreview(
        pages_to_create=to_create,
        pages_to_delete=to_delete,
        pages_preserved_user_edited=user_edited,
        source_file_count=len(source_files),
        estimated_tokens=estimated_tokens,
    )


async def handle_rebuild(
    session: AsyncSession,
    class_id: uuid.UUID,
    *,
    task_id: str | None = None,
) -> RebuildResult:
    """Rebuild the entire wiki from source files, preserving user-edited pages.

    Each source file is re-ingested in its own transaction (via ingest_source).
    If the process is interrupted, the wiki will be in a partially-rebuilt state;
    re-running /rebuild will complete it. This is acceptable for a local app.
    """
    from app.services.task_manager import task_manager

    cid = str(class_id)
    wp = init_wiki_repo(cid)
    pages_dir = wp / "pages"

    user_edited_paths: list[str] = []
    deleted_count = 0

    if pages_dir.exists():
        for md_file in list(pages_dir.rglob("*.md")):
            rel_path = md_file.relative_to(wp).as_posix()
            content = md_file.read_text(encoding="utf-8")
            if "user_edited: true" in content[:500]:
                user_edited_paths.append(rel_path)
            else:
                md_file.unlink()
                deleted_count += 1

    await session.execute(
        delete(WikiPage).where(
            WikiPage.class_id == class_id,
            WikiPage.path.notin_(user_edited_paths),
        )
    )
    await session.flush()

    source_files_q = await session.execute(
        select(File).where(File.class_id == class_id, File.status == FileStatus.READY)
    )
    source_files = source_files_q.scalars().all()

    total = len(source_files)
    created_count = 0

    for i, file_record in enumerate(source_files):
        if task_id and task_manager.is_cancelled(task_id):
            commit_wiki_change(cid, "rebuild: cancelled (partial)")
            return RebuildResult(
                success=False,
                pages_created=created_count,
                pages_deleted=deleted_count,
                pages_preserved=len(user_edited_paths),
                error="Cancelled by user",
            )

        if task_id:
            pct = int(((i + 1) / max(total, 1)) * 100)
            task_manager.update_progress(
                task_id, pct, f"Re-ingesting {file_record.original_filename} ({i + 1}/{total})"
            )

        ingest_result = await ingest_source(session, class_id, file_record.id)
        if ingest_result.success:
            created_count += len(ingest_result.pages_created) + len(ingest_result.pages_updated)

    index_content = _rebuild_index_from_disk(wp)
    _write_index(wp, index_content)
    append_log(
        wp,
        "rebuild",
        f"{total} sources",
        f"Created: {created_count}, Deleted: {deleted_count}, "
        f"Preserved (user-edited): {len(user_edited_paths)}\n",
    )
    await session.commit()
    commit_wiki_change(cid, f"rebuild: {total} sources re-ingested")

    return RebuildResult(
        success=True,
        pages_created=created_count,
        pages_deleted=deleted_count,
        pages_preserved=len(user_edited_paths),
    )


# ---------------------------------------------------------------------------
# Streaming support (Task 3B.13)
# ---------------------------------------------------------------------------


async def handle_ask_stream(
    session: AsyncSession,
    class_id: uuid.UUID,
    query: str,
) -> AsyncIterator[str]:
    """Stream an /ask response token-by-token."""
    cid = str(class_id)

    search_results = await hybrid_search(session, class_id, query, limit=10)

    wp = wiki_dir(cid)
    pages_context: list[str] = []
    pages_consulted: list[str] = []
    token_budget = 90_000

    index_path = wp / "index.md"
    if index_path.exists():
        index_text = index_path.read_text(encoding="utf-8")
        pages_context.append(f"## Wiki Index\n\n{index_text}")
        token_budget -= _count_tokens(index_text)

    for sr in search_results:
        page_file = wp / sr.path
        if not page_file.exists():
            continue
        page_content = page_file.read_text(encoding="utf-8")
        page_tokens = _count_tokens(page_content)
        if page_tokens > token_budget:
            break
        pages_context.append(f"## Page: {sr.title}\nPath: {sr.path}\n\n{page_content}")
        pages_consulted.append(sr.path)
        token_budget -= page_tokens

    if not pages_consulted:
        msg = "I don't have any wiki pages yet to answer your question. Try uploading some source material first."
        await _save_chat_messages(session, class_id, query, msg, "ask")
        yield msg
        return

    separator = "---\n"
    context_block = separator.join(pages_context)
    user_prompt = f"## Context\n\n{context_block}\n\n---\n\n## Question\n\n{query}"

    collected: list[str] = []
    try:
        provider = get_llm_provider()
        async for chunk in provider.stream(
            ASK_SYSTEM_PROMPT, user_prompt, max_tokens=settings.llm_max_tokens
        ):
            collected.append(chunk)
            yield chunk
    except (OSError, ValueError, RuntimeError) as e:
        logger.error("ask_stream_error", class_id=cid, error=str(e))
        error_msg = f"\n\n[Error: {e}]"
        collected.append(error_msg)
        yield error_msg

    full_answer = "".join(collected)
    await _save_chat_messages(session, class_id, query, full_answer, "ask")
