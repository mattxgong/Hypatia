"""Core wiki engine: source ingestion and /ask query handling (Tasks 3A.5, 3A.7).

Orchestrates the LLM wiki pattern: reads converted source material, prompts
the LLM to generate wiki pages, parses output, writes pages to disk and DB,
and answers user queries from the wiki.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import tiktoken
from sqlalchemy import select
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
from app.services.prompts.wiki_schema import WIKI_SCHEMA
from app.services.wiki_git import commit_wiki_change, init_wiki_repo, wiki_dir
from app.services.wiki_parser import ParsedWikiPage, parse_llm_output
from app.services.wiki_search import search_wiki_pages, sync_fts_page
from app.utils.logging import get_logger

logger = get_logger()

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


_INGEST_SYSTEM_PROMPT = f"""\
{WIKI_SCHEMA}

## Your Task

You are ingesting a source document into the wiki. You must:

1. Create a **source-summary** page summarizing the document.
2. Identify key **concepts** and **entities** mentioned in the source.
3. For each concept/entity: create a new page OR update an existing one \
(use action="update" if the page already exists in the index).
4. Include citations linking claims back to the source using the \
hypatia://cite format described above.
5. Add cross-references between pages using [[wiki-links]].

Output ONLY <wiki-page> tags. No other text before or after.
"""

_ASK_SYSTEM_PROMPT = f"""\
{WIKI_SCHEMA}

## Your Task

You are answering a user's question using the wiki pages provided as context.

Rules:
1. Answer based ONLY on information found in the provided wiki pages.
2. Cite specific wiki pages and their original sources in your answer.
3. Use markdown formatting for your response.
4. If the wiki does not contain enough information to answer, say so clearly.
5. Include inline citations using the hypatia://cite format when referencing \
claims from sources.
6. Reference wiki pages with [[page-slug]] links where relevant.
"""


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
                _INGEST_SYSTEM_PROMPT, user_prompt, max_tokens=settings.llm_max_tokens
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

    search_results = await search_wiki_pages(session, class_id, query, limit=10)

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
            _ASK_SYSTEM_PROMPT, user_prompt, max_tokens=settings.llm_max_tokens
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
    results = await search_wiki_pages(session, class_id, query_hint, limit=5)

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
    """Append an entry to log.md."""
    log_file = wiki_path / "log.md"
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    entry = f"\n## [{timestamp}] {action} | {detail}\n"
    if result.pages_created:
        entry += f"Created: {', '.join(result.pages_created)}\n"
    if result.pages_updated:
        entry += f"Updated: {', '.join(result.pages_updated)}\n"

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
