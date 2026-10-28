"""Core wiki engine: all commands (Phase 3A + 3B).

Orchestrates the LLM wiki pattern: reads converted source material, prompts
the LLM to generate wiki pages, parses output, stores pages, and answers user
queries from the wiki. Also provides wiki page CRUD, export, and the commands
/summarize, /remove, /lint, /rebuild.

Pages live in the database (``wiki_pages``), the single source of truth. Each
operation commits first and then mirrors the result to disk and git with
``wiki_store.mirror_to_disk``; see that module for the details.
"""

from __future__ import annotations

import io
import json
import re
import uuid
import zipfile
from collections import deque
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

import tiktoken
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import ErrorCode, HypatiaError
from app.models.db_models import (
    ChatMessage,
    ChatRole,
    File,
    FileStatus,
    WikiCategory,
    WikiPage,
)
from app.services import storage_service
from app.services.llm_providers.base import LLMProvider
from app.services.llm_service import get_context_window, get_llm_provider
from app.services.prompts.ingest_prompt import INGEST_SYSTEM_PROMPT
from app.services.prompts.lint_prompt import LINT_SYSTEM_PROMPT
from app.services.prompts.query_prompt import ASK_SYSTEM_PROMPT
from app.services.prompts.summarize_prompt import SUMMARIZE_SYSTEM_PROMPT
from app.services.prompts.wiki_schema import WIKI_SCHEMA
from app.services.wiki_git import read_pages_at
from app.services.wiki_parser import (
    ParsedWikiPage,
    normalize_page_path,
    page_body,
    parse_llm_output,
    parse_page_document,
)
from app.services.wiki_search import (
    delete_fts_page,
    hybrid_search,
    sync_fts_page,
)
from app.services.wiki_store import (
    append_log,
    build_index,
    class_operation_lock,
    load_index,
    load_pages,
    mirror_to_disk,
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

#: Smallest prompt budget worth attempting, so a misconfigured context window
#: degrades into small prompts rather than empty ones.
_MIN_PROMPT_BUDGET = 512

#: Fractions of the usable prompt budget allotted to each kind of context.
_SOURCE_BUDGET_RATIO = 0.50  # the source document being ingested
_RELATED_PAGES_RATIO = 0.30  # existing pages shown so the LLM can cross-link
_ASK_CONTEXT_RATIO = 0.75  # wiki pages retrieved to answer a question
_ASK_INDEX_RATIO = 0.25  # share of the /ask context the index may take

#: Share of the context window kept free: tiktoken's counts differ from the
#: model's own tokenizer, and prompts add headers around each part.
_PROMPT_HEADROOM_RATIO = 0.05

#: A chunk whose ingest output was cut off is split and retried, down to this.
_MIN_SPLIT_TOKENS = 400

#: An update keeps the old page if its body shrinks below this share of the
#: old body's length; an LLM rewriting from one source tends to drop the rest.
_MIN_UPDATE_LENGTH_RATIO = 0.6

#: Page headers file_converter writes into converted PDFs.
_PAGE_MARKER_LINE = re.compile(r"^\*\*\[Page \d+\]\*\*$")

#: `[[slug]]` or `[[slug|display text]]`.
_WIKI_LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")

#: Wiki exports older than this are removed when a new one is made.
_EXPORT_RETENTION_SECONDS = 24 * 60 * 60

#: The file a citation link points at.
_CITATION_FILE = re.compile(r"hypatia://cite\?file=([^&)\s\"]+)")


def _output_budget() -> int:
    """Tokens to allow the model to generate.

    Capped at a quarter of the context window: with a small local model,
    ``llm_max_tokens`` alone can exceed the whole window.
    """
    return max(min(settings.llm_max_tokens, get_context_window() // 4), 256)


def _prompt_budget(system_prompt: str = "") -> int:
    """Tokens available for a user prompt sent with ``system_prompt``.

    Reserves the response budget, the system prompt itself and some headroom.
    Every prompt built in this module is sized against this. Exceeding the
    model's window is not a soft truncation — Ollama rejects the request with
    a 400 ``exceed_context_size_error``.
    """
    window = get_context_window()
    available = (
        window
        - _output_budget()
        - _count_tokens(system_prompt)
        - int(window * _PROMPT_HEADROOM_RATIO)
    )
    return max(available, _MIN_PROMPT_BUDGET)


@asynccontextmanager
async def _llm() -> AsyncIterator[LLMProvider]:
    """The configured provider, closed afterwards. Copilot's holds a CLI process."""
    provider = get_llm_provider()
    try:
        yield provider
    finally:
        await provider.close()


def _get_encoder() -> tiktoken.Encoding:
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return _ENCODER


def _count_tokens(text: str) -> int:
    return len(_get_encoder().encode(text))


def _truncate_to_tokens(text: str, budget: int) -> str:
    """Cut ``text`` down to ``budget`` tokens, noting that it was cut."""
    encoder = _get_encoder()
    tokens = encoder.encode(text)
    if len(tokens) <= budget:
        return text
    return encoder.decode(tokens[:budget]) + "\n\n[... truncated ...]"


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

    id: uuid.UUID
    path: str
    title: str
    category: str
    user_edited: bool
    updated_at: datetime


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
    #: Regenerated from sources; removed if the rebuilt wiki no longer has them.
    pages_to_delete: list[str]
    pages_preserved_user_edited: list[str]
    source_file_count: int
    estimated_tokens: int
    pages_preserved_synthesis: list[str] = field(default_factory=list)


@dataclass
class RebuildResult:
    """Result of a /rebuild operation."""

    success: bool
    pages_created: int = 0
    pages_deleted: int = 0
    pages_preserved: int = 0
    error: str | None = None
    #: Pages that existed before and were not regenerated.
    pages_removed: list[str] = field(default_factory=list)
    #: Old pages put back because their source could not be re-ingested.
    pages_restored: list[str] = field(default_factory=list)
    #: Sources whose re-ingest failed, as "filename: error".
    failed_sources: list[str] = field(default_factory=list)


@dataclass
class _PendingPage:
    """A page generated during an ingest, held until every chunk succeeds."""

    parsed: ParsedWikiPage
    content: str
    created: bool


async def ingest_source(
    session: AsyncSession,
    class_id: uuid.UUID,
    file_id: uuid.UUID,
    *,
    task_id: str | None = None,
) -> IngestResult:
    """Ingest a converted source file into the wiki.

    The LLM's pages are collected in memory across chunks and written in one
    transaction once every chunk has succeeded, so a cancel or failure leaves
    the wiki untouched and SQLite is never write-locked while the LLM runs.

    The caller must hold ``class_operation_lock(class_id)``.
    """
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
    metadata = dict(file_record.metadata_json or {})
    if metadata.get("token_count") != source_tokens:
        metadata["token_count"] = source_tokens
        file_record.metadata_json = metadata

    prompt_budget = _prompt_budget(INGEST_SYSTEM_PROMPT)
    source_budget = int(prompt_budget * _SOURCE_BUDGET_RATIO)
    related_budget = int(prompt_budget * _RELATED_PAGES_RATIO)
    index_budget = prompt_budget - source_budget - related_budget

    chunks = (
        _chunk_source(source_content, source_budget)
        if source_tokens > source_budget
        else [source_content]
    )

    provider = get_llm_provider()
    try:
        return await _ingest_chunks(
            session,
            class_id,
            file_record,
            chunks,
            provider,
            task_id=task_id,
            related_budget=related_budget,
            index_budget=index_budget,
        )
    finally:
        await provider.close()


async def _ingest_chunks(
    session: AsyncSession,
    class_id: uuid.UUID,
    file_record: File,
    chunks: list[str],
    provider: LLMProvider,
    *,
    task_id: str | None,
    related_budget: int,
    index_budget: int,
) -> IngestResult:
    from app.services.task_manager import task_manager

    cid = str(class_id)
    file_id = file_record.id
    filename = file_record.original_filename
    file_record.status = FileStatus.PROCESSING
    await session.commit()
    logger.info("ingest_started", class_id=cid, file_id=str(file_id), chunks=len(chunks))

    existing = {p.path: p for p in await load_pages(session, class_id)}
    pending: dict[str, _PendingPage] = {}

    remaining = deque(chunks)
    # Progress is the share of the source done, so re-splitting a cut-off
    # chunk adds parts without moving the bar backwards.
    source_tokens = max(sum(_count_tokens(c) for c in chunks), 1)
    done_tokens = 0
    i = 0
    while remaining:
        chunk = remaining.popleft()
        total = i + 1 + len(remaining)
        if task_id:
            if task_manager.is_cancelled(task_id):
                return IngestResult(success=False, error="Cancelled by user")
            if total > 1:
                task_manager.update_progress(
                    task_id,
                    min(done_tokens * 100 // source_tokens, 99),
                    f"Ingesting {filename} (part {i + 1}/{total})",
                )
            else:
                task_manager.update_progress(task_id, None, f"Ingesting {filename}")

        shown = await _pages_for_context(
            session, class_id, chunk, existing, pending, related_budget
        )
        # End the read transaction: held open through the LLM call, its SQLite
        # lock would block other writers for the whole call.
        await session.commit()
        user_prompt = _build_ingest_prompt(
            chunk,
            filename,
            str(file_id),
            _truncate_to_tokens(_index_with_pending(existing, pending), index_budget),
            _format_shown_pages(shown),
            i,
            total,
        )

        try:
            raw_output = await provider.complete(
                INGEST_SYSTEM_PROMPT, user_prompt, max_tokens=_output_budget()
            )
        except HypatiaError as e:
            if e.code == ErrorCode.LLM_RATE_LIMITED:
                # Nothing was written; READY lets the queue's retry start over.
                file_record.status = FileStatus.READY
                await session.commit()
                raise
            logger.error("ingest_llm_error", class_id=cid, file_id=str(file_id), error=str(e))
            return IngestResult(success=False, error=f"LLM error: {e}")
        except (OSError, ValueError, RuntimeError) as e:
            logger.error("ingest_llm_error", class_id=cid, file_id=str(file_id), error=str(e))
            return IngestResult(success=False, error=f"LLM error: {e}")

        if provider.last_truncated is True:
            # The last page of a cut-off response is lost, so redo the chunk
            # in smaller parts while it can still be split.
            parts = _chunk_source(chunk, max(_count_tokens(chunk) // 2, 1))
            if len(parts) > 1 and _count_tokens(chunk) > _MIN_SPLIT_TOKENS:
                logger.warning("ingest_output_truncated_splitting", file_id=str(file_id), chunk=i)
                remaining.extendleft(reversed(parts))
                continue
            logger.warning("ingest_output_truncated", file_id=str(file_id), chunk=i)

        i += 1
        done_tokens += _count_tokens(chunk)
        pages = parse_llm_output(raw_output)
        if not pages:
            logger.warning("ingest_no_pages_parsed", class_id=cid, file_id=str(file_id), chunk=i)
            if total == 1:
                return IngestResult(success=False, error="LLM produced no parseable wiki pages")
            continue

        for page in pages:
            _stage_page(page, file_id, existing, pending, shown)

    # A user may have edited a page while the LLM was running.
    current = await _pages_by_path(session, class_id, pending, refresh=True)
    result = IngestResult(success=True)
    for path, staged in pending.items():
        row = current.get(path)
        if row is not None and row.user_edited:
            logger.info("skip_user_edited_page", path=path)
            continue
        await _store_page(
            session,
            class_id,
            row,
            staged.parsed,
            staged.content,
            source_ids=[str(file_id), *staged.parsed.sources],
        )
        (result.pages_created if staged.created else result.pages_updated).append(path)

    file_record.status = FileStatus.READY
    await session.commit()

    append_log(cid, "ingest", filename, _ingest_log_details(result))
    await mirror_to_disk(session, class_id, f"ingest: {filename}")
    logger.info(
        "ingest_complete",
        class_id=cid,
        file_id=str(file_id),
        created=len(result.pages_created),
        updated=len(result.pages_updated),
    )
    return result


def _stage_page(
    page: ParsedWikiPage,
    file_id: uuid.UUID,
    existing: dict[str, WikiPage],
    pending: dict[str, _PendingPage],
    shown: dict[str, str],
) -> None:
    """Hold an LLM page for writing, unless it would lose content.

    Whether a page is new or an update is decided by what exists, not by the
    LLM's ``action``. The LLM may only update pages it was shown in this
    prompt; an update that drops citations or most of the text keeps the old
    version, since a rewrite from one source tends to lose the others.
    """
    row = existing.get(page.path)
    if row is not None and row.user_edited:
        logger.info("skip_user_edited_page", path=page.path)
        return

    previous = pending[page.path].content if page.path in pending else None
    if previous is None and row is not None:
        previous = row.content
    if previous is not None:
        if page.path not in shown:
            logger.warning("ingest_update_of_unseen_page_skipped", path=page.path)
            return
        problem = _update_loses_content(page_body(previous), page.content)
        if problem:
            logger.warning("ingest_update_rejected", path=page.path, reason=problem)
            return

    pending[page.path] = _PendingPage(
        parsed=page,
        content=_render_page_content(page, file_id),
        created=row is None,
    )


def _update_loses_content(old_body: str, new_body: str) -> str | None:
    """Why replacing ``old_body`` with ``new_body`` would lose content, if it would."""
    dropped = set(_CITATION_FILE.findall(old_body)) - set(_CITATION_FILE.findall(new_body))
    if dropped:
        return f"drops citations of {', '.join(sorted(dropped))}"
    if len(new_body.strip()) < len(old_body.strip()) * _MIN_UPDATE_LENGTH_RATIO:
        return "much shorter than the current page"
    return None


async def _pages_for_context(
    session: AsyncSession,
    class_id: uuid.UUID,
    chunk: str,
    existing: dict[str, WikiPage],
    pending: dict[str, _PendingPage],
    budget: int,
) -> dict[str, str]:
    """Pages to show the LLM with their current text: those already generated
    from this source first, then the existing pages most related to the chunk.
    User-edited pages are left out, since they can't be updated anyway.
    """
    candidates: list[tuple[str, str]] = [(p, staged.content) for p, staged in pending.items()]
    for sr in await hybrid_search(session, class_id, chunk[:1000], limit=5):
        row = existing.get(sr.path)
        if row is not None and not row.user_edited and sr.path not in pending:
            candidates.append((sr.path, row.content))

    shown: dict[str, str] = {}
    used = 0
    for path, content in candidates:
        tokens = _count_tokens(content)
        if used + tokens > budget:
            continue
        shown[path] = content
        used += tokens
    return shown


def _format_shown_pages(shown: dict[str, str]) -> str:
    return "\n\n---\n\n".join(f"### {path}\n\n{content}" for path, content in shown.items())


@dataclass
class _IndexEntry:
    path: str
    title: str
    category: WikiCategory
    source_file_ids: list[str] | None


def _index_with_pending(existing: dict[str, WikiPage], pending: dict[str, _PendingPage]) -> str:
    """The index as it will be once the pending pages are written."""
    entries: dict[str, _IndexEntry | WikiPage] = dict(existing)
    for path, staged in pending.items():
        if path not in existing:
            entries[path] = _IndexEntry(
                path=path,
                title=staged.parsed.title,
                category=WikiCategory(staged.parsed.category),
                source_file_ids=staged.parsed.sources,
            )
    return build_index(list(entries.values()))  # type: ignore[arg-type]


def _ingest_log_details(result: IngestResult) -> str:
    details = ""
    if result.pages_created:
        details += f"Created: {', '.join(result.pages_created)}\n"
    if result.pages_updated:
        details += f"Updated: {', '.join(result.pages_updated)}\n"
    return details


async def _pages_by_path(
    session: AsyncSession,
    class_id: uuid.UUID,
    paths: Iterable[str],
    *,
    refresh: bool = False,
) -> dict[str, WikiPage]:
    wanted = list(paths)
    if not wanted:
        return {}
    query = select(WikiPage).where(WikiPage.class_id == class_id, WikiPage.path.in_(wanted))
    if refresh:
        query = query.execution_options(populate_existing=True)
    return {p.path: p for p in (await session.execute(query)).scalars()}


async def _store_page(
    session: AsyncSession,
    class_id: uuid.UUID,
    row: WikiPage | None,
    page: ParsedWikiPage,
    content: str,
    *,
    source_ids: list[str],
    category: WikiCategory | None = None,
    replace_sources: bool = False,
) -> WikiPage:
    """Create or update a page row and its search index entries."""
    category = category or WikiCategory(page.category)
    if row is None:
        row = WikiPage(
            class_id=class_id,
            path=page.path,
            title=page.title,
            category=category,
            content=content,
            source_file_ids=_unique(source_ids),
        )
        session.add(row)
    else:
        row.title = page.title
        row.category = category
        row.content = content
        row.source_file_ids = _unique(
            source_ids if replace_sources else [*(row.source_file_ids or []), *source_ids]
        )
        row.updated_at = datetime.now(UTC)
    await session.flush()

    await sync_fts_page(
        session,
        page_id=row.id,
        class_id=class_id,
        path=page.path,
        title=page.title,
        content=page.content,
        tags=page.tags,
    )
    await _upsert_embedding_safe(session, row.id, page.content)
    return row


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(v) for v in values))


async def _delete_page(session: AsyncSession, row: WikiPage) -> None:
    await delete_fts_page(session, row.id)
    await _delete_embedding_safe(session, row.id)
    await session.delete(row)


async def _ask_context(
    session: AsyncSession, class_id: uuid.UUID, query: str, *, search_text: str | None = None
) -> tuple[list[str], list[str]]:
    """The context blocks for an /ask prompt, and the paths of pages included."""
    search_results = await hybrid_search(session, class_id, search_text or query, limit=10)
    rows = await _pages_by_path(session, class_id, [sr.path for sr in search_results])

    pages_context: list[str] = []
    pages_consulted: list[str] = []
    token_budget = int(_prompt_budget(ASK_SYSTEM_PROMPT) * _ASK_CONTEXT_RATIO)

    if rows:
        # Bounded: the index grows with the wiki and would crowd out the pages.
        index_text = _truncate_to_tokens(
            await load_index(session, class_id), int(token_budget * _ASK_INDEX_RATIO)
        )
        pages_context.append(f"## Wiki Index\n\n{index_text}")
        token_budget -= _count_tokens(index_text)

    for sr in search_results:
        row = rows.get(sr.path)
        if row is None:
            continue
        page_tokens = _count_tokens(row.content)
        if page_tokens > token_budget:
            continue  # a smaller, lower-ranked page may still fit
        pages_context.append(f"## Page: {sr.title}\nPath: {sr.path}\n\n{row.content}")
        pages_consulted.append(sr.path)
        token_budget -= page_tokens
    return pages_context, pages_consulted


_NO_PAGES_ANSWER = (
    "I don't have any wiki pages yet to answer your question. "
    "Try uploading some source material first."
)


async def handle_ask(
    session: AsyncSession,
    class_id: uuid.UUID,
    query: str,
) -> AskResult:
    """Answer a user question by searching the wiki and prompting the LLM."""
    cid = str(class_id)
    pages_context, pages_consulted = await _ask_context(session, class_id, query)

    if not pages_consulted:
        await _save_chat_messages(session, class_id, query, _NO_PAGES_ANSWER, "ask")
        return AskResult(answer=_NO_PAGES_ANSWER, pages_consulted=[])

    context_block = "---\n".join(pages_context)
    user_prompt = f"## Context\n\n{context_block}\n\n---\n\n## Question\n\n{query}"

    try:
        async with _llm() as provider:
            answer = await provider.complete(
                ASK_SYSTEM_PROMPT, user_prompt, max_tokens=_output_budget()
            )
    except (OSError, ValueError, RuntimeError, HypatiaError) as e:
        logger.error("ask_llm_error", class_id=cid, error=str(e))
        answer = f"Error generating answer: {e}"

    await _save_chat_messages(session, class_id, query, answer, "ask")
    return AskResult(answer=answer, pages_consulted=pages_consulted)


def _format_history(history: list[tuple[str, str]], budget: int) -> str:
    """The latest turns that fit in ``budget`` tokens, oldest first."""
    kept: list[str] = []
    used = 0
    for role, text in reversed(history):
        line = f"{'Student' if role == 'user' else 'You'}: {text}"
        tokens = _count_tokens(line)
        if used + tokens > budget:
            break
        kept.append(line)
        used += tokens
    return "\n\n".join(reversed(kept))


def _chunk_source(content: str, token_budget: int) -> list[str]:
    """Split source content into chunks that fit within the token budget."""
    encoder = _get_encoder()
    lines = content.split("\n")
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_tokens = 0
    page_marker: str | None = None

    for line in lines:
        line_tokens = len(encoder.encode(line + "\n"))
        if current_tokens + line_tokens > token_budget and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_tokens = 0
            # A chunk that starts mid-page still needs to know which page it is on.
            if page_marker is not None and not _PAGE_MARKER_LINE.match(line):
                current_chunk.append(page_marker)
                current_tokens += len(encoder.encode(page_marker + "\n"))
        if _PAGE_MARKER_LINE.match(line):
            page_marker = line
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
        parts.append(
            "## Existing Pages You May Update\n\n"
            "These are the current versions. To update one, return its full new "
            "content, keeping what is still accurate and every existing citation. "
            "Do not update an existing page that is not shown here; link to it "
            "instead.\n\n"
            f"{existing_pages}"
        )

    chunk_note = ""
    if total_chunks > 1:
        chunk_note = (
            f"\n\nNote: This is chunk {chunk_index + 1} of {total_chunks}. "
            f"{'Create new pages for this content.' if chunk_index == 0 else 'Update the pages created from earlier chunks (shown above), or create new ones as needed.'}"
        )

    parts.append(
        f"## Source Document\n\n"
        f"Filename: {filename}\n"
        f"File ID: {file_id}\n"
        f"{chunk_note}\n\n"
        f"---\n\n{source_content}"
    )
    return "\n\n".join(parts)


def _render_page_content(page: ParsedWikiPage, file_id: uuid.UUID | None) -> str:
    """Render a parsed page back into markdown with frontmatter."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    sources = page.sources or ([str(file_id)] if file_id else [])
    tags_str = ", ".join(page.tags) if page.tags else ""
    sources_str = ", ".join(sources)
    title = page.title.replace("\\", "\\\\").replace('"', '\\"')

    return (
        f"---\n"
        f'title: "{title}"\n'
        f"type: {page.category}\n"
        f"sources: [{sources_str}]\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f"tags: [{tags_str}]\n"
        f"user_edited: false\n"
        f"---\n\n"
        f"{page.content}\n"
    )


def _extract_title_from_content(content: str) -> str:
    """Extract title from YAML frontmatter."""
    for line in content.split("\n")[:10]:
        line = line.strip()
        if line.startswith("title:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


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
# Public API: CRUD, index, export (Tasks 3B.1, 3B.6, 3B.7)
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
    return [
        WikiTreeNode(
            id=page.id,
            path=page.path,
            title=page.title,
            category=page.category.value,
            user_edited=page.user_edited,
            updated_at=page.updated_at,
        )
        for page in result.scalars().all()
    ]


async def get_wiki_page(
    session: AsyncSession,
    class_id: uuid.UUID,
    page_path: str,
) -> WikiPageContent | None:
    """A wiki page's full content. ``index.md`` is generated from the pages."""
    if page_path == "index.md":
        return WikiPageContent(
            path=page_path,
            title="Wiki Index",
            category=WikiCategory.INDEX.value,
            content=await load_index(session, class_id),
            user_edited=False,
            source_file_ids=[],
        )

    row = (await _pages_by_path(session, class_id, [page_path])).get(page_path)
    if row is None:
        return None
    return WikiPageContent(
        path=row.path,
        title=row.title,
        category=row.category.value,
        content=row.content,
        user_edited=row.user_edited,
        source_file_ids=[str(s) for s in row.source_file_ids or []],
    )


async def get_wiki_context(session: AsyncSession, class_id: uuid.UUID) -> str:
    """Return the wiki schema + current index for LLM prompting."""
    pages = await load_pages(session, class_id)
    parts = [WIKI_SCHEMA]
    if pages:
        parts.append(f"\n\n## Current Wiki Index\n\n{build_index(pages)}")
    return "\n".join(parts)


async def update_wiki_page(
    session: AsyncSession,
    class_id: uuid.UUID,
    page_path: str,
    content: str,
    *,
    is_user_edit: bool = False,
) -> None:
    """Store new content for a wiki page (creating it if needed), update search."""
    safe_path = normalize_page_path(page_path)
    if safe_path is None:
        raise HypatiaError(ErrorCode.VALIDATION_ERROR, f"Invalid wiki page path: {page_path!r}")
    page_path = safe_path

    if is_user_edit:
        content = _ensure_user_edited_flag(content)

    title = _extract_title_from_content(content) or Path(page_path).stem
    category_str = "concept"
    tags: list[str] = []
    for line in content.split("\n")[:15]:
        stripped = line.strip()
        if stripped.startswith("type:") and category_str == "concept":
            category_str = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("tags:") and not tags:
            raw = stripped.split(":", 1)[1].strip().strip("[]")
            tags = [t.strip() for t in raw.split(",") if t.strip()]

    try:
        category = WikiCategory(category_str)
    except ValueError:
        category = WikiCategory.CONCEPT

    row = (await _pages_by_path(session, class_id, [page_path])).get(page_path)
    if row is None:
        row = WikiPage(
            class_id=class_id,
            path=page_path,
            title=title,
            category=category,
            content=content,
            source_file_ids=[],
        )
        session.add(row)
    else:
        row.title = title
        row.category = category
        row.content = content
        row.updated_at = datetime.now(UTC)
    if is_user_edit:
        row.user_edited = True
    await session.flush()

    await sync_fts_page(
        session,
        page_id=row.id,
        class_id=class_id,
        path=page_path,
        title=title,
        content=content,
        tags=tags,
    )
    await _upsert_embedding_safe(session, row.id, content)
    await session.commit()

    verb = "user-edit" if is_user_edit else "edit"
    await mirror_to_disk(session, class_id, f"{verb}: modified {page_path}")


def _ensure_user_edited_flag(content: str) -> str:
    """Set user_edited: true in frontmatter, adding if missing.

    The ``user_edited`` column is what the app checks; the flag keeps the page
    text honest for the LLM (which is told not to modify such pages) and for
    exported markdown.
    """
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


async def handle_export(
    session: AsyncSession,
    class_id: uuid.UUID,
    export_format: str = "zip",
) -> ExportResult:
    """Export the wiki as a ZIP archive."""
    cid = str(class_id)
    pages = [p for p in await load_pages(session, class_id) if p.path.startswith("pages/")]
    if not pages:
        return ExportResult(success=False, error="No wiki pages to export")

    export_dir = settings.data_dir / "exports" / cid
    export_dir.mkdir(parents=True, exist_ok=True)
    # Exports kept for the chat command's message; older ones just take space.
    cutoff = datetime.now(UTC).timestamp() - _EXPORT_RETENTION_SECONDS
    for old in export_dir.glob("wiki_*.zip"):
        if old.stat().st_mtime < cutoff:
            old.unlink(missing_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    zip_path = export_dir / f"wiki_{timestamp}.zip"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.md", build_index(pages))
        for page in sorted(pages, key=lambda p: p.path):
            zf.writestr(page.path, page.content)
    zip_path.write_bytes(buffer.getvalue())

    append_log(cid, "export", f"{export_format} ({len(pages)} pages)")
    logger.info("wiki_exported", class_id=cid, page_count=len(pages), path=str(zip_path))
    return ExportResult(success=True, export_path=str(zip_path), page_count=len(pages))


# ---------------------------------------------------------------------------
# Commands: /summarize, /remove, /lint, /rebuild (Tasks 3B.2-5)
# ---------------------------------------------------------------------------


async def handle_summarize(
    session: AsyncSession,
    class_id: uuid.UUID,
    topic: str,
) -> SummarizeResult:
    """Synthesize a summary page from wiki pages relevant to the topic."""
    async with class_operation_lock(class_id):
        return await _summarize(session, class_id, topic)


async def _summarize(session: AsyncSession, class_id: uuid.UUID, topic: str) -> SummarizeResult:
    cid = str(class_id)
    search_results = await hybrid_search(session, class_id, topic, limit=10)
    if not search_results:
        return SummarizeResult(success=False, error="No wiki pages found for this topic")

    rows = await _pages_by_path(session, class_id, [sr.path for sr in search_results])
    pages_context: list[str] = []
    token_budget = int(_prompt_budget(SUMMARIZE_SYSTEM_PROMPT) * 0.9) - _count_tokens(topic)
    for sr in search_results:
        row = rows.get(sr.path)
        if row is None:
            continue
        tokens = _count_tokens(row.content)
        if tokens > token_budget:
            continue
        pages_context.append(f"## Page: {sr.title}\nPath: {sr.path}\n\n{row.content}")
        token_budget -= tokens

    if not pages_context:
        return SummarizeResult(success=False, error="No readable pages found")

    context_block = "\n\n---\n\n".join(pages_context)
    user_prompt = f"## Topic to Summarize\n\n{topic}\n\n---\n\n## Source Pages\n\n{context_block}"

    try:
        async with _llm() as provider:
            raw_output = await provider.complete(
                SUMMARIZE_SYSTEM_PROMPT, user_prompt, max_tokens=_output_budget()
            )
    except (OSError, ValueError, RuntimeError, HypatiaError) as e:
        logger.error("summarize_llm_error", class_id=cid, error=str(e))
        return SummarizeResult(success=False, error=f"LLM error: {e}")

    pages = parse_llm_output(raw_output)
    if not pages:
        return SummarizeResult(success=False, error="LLM produced no parseable output")

    page = pages[0]
    row = (await _pages_by_path(session, class_id, [page.path])).get(page.path)
    if row is not None and row.user_edited:
        return SummarizeResult(
            success=False, error=f"{page.path} has your edits, so it was not overwritten"
        )
    await _store_page(
        session,
        class_id,
        row,
        page,
        _render_page_content(page, None),
        source_ids=page.sources,
        category=WikiCategory.SYNTHESIS,
        replace_sources=True,
    )
    await session.commit()

    append_log(cid, "summarize", topic, f"Created: {page.path}\n")
    await mirror_to_disk(session, class_id, f"summarize: {topic}")
    return SummarizeResult(success=True, page_path=page.path)


async def handle_remove(
    session: AsyncSession,
    class_id: uuid.UUID,
    filename: str,
) -> RemoveResult:
    """Remove a source file and clean up all associated wiki content."""
    from app.services.ingestion_queue import get_ingestion_queue

    file_id = (
        await session.execute(
            select(File.id).where(File.class_id == class_id, File.original_filename == filename)
        )
    ).scalar_one_or_none()
    if file_id is None:
        return RemoveResult(success=False, error=f"File not found: {filename}")

    # Before taking the lock: if this file is being ingested, the ingest holds
    # it, and cancelling it is what releases it.
    await get_ingestion_queue().cancel_file(class_id, file_id)
    async with class_operation_lock(class_id):
        return await _remove(session, class_id, filename)


async def _remove(session: AsyncSession, class_id: uuid.UUID, filename: str) -> RemoveResult:
    cid = str(class_id)
    result_q = await session.execute(
        select(File)
        .where(File.class_id == class_id, File.original_filename == filename)
        .execution_options(populate_existing=True)
    )
    file_record = result_q.scalar_one_or_none()
    if file_record is None:
        return RemoveResult(success=False, error=f"File not found: {filename}")

    file_id = str(file_record.id)
    raw_path = file_record.raw_path
    converted_path = file_record.converted_path

    result = RemoveResult(success=True)
    remaining: list[WikiPage] = []
    for page in await load_pages(session, class_id):
        sources = [str(s) for s in page.source_file_ids or []]
        if file_id not in sources:
            remaining.append(page)
            continue
        # A page only this file supported goes too, unless the user edited it.
        if len(sources) == 1 and not page.user_edited:
            await _delete_page(session, page)
            result.pages_deleted.append(page.path)
        else:
            page.source_file_ids = [s for s in sources if s != file_id]
            page.updated_at = datetime.now(UTC)
            remaining.append(page)
            result.pages_updated.append(page.path)

    result.dead_links_cleaned = await _clean_dead_links(
        session, class_id, remaining, result.pages_deleted
    )
    await session.delete(file_record)
    await session.commit()

    # Only once the database no longer references them.
    if raw_path:
        Path(raw_path).unlink(missing_ok=True)
    if converted_path:
        converted = Path(converted_path)
        converted.unlink(missing_ok=True)
        converted.with_suffix(".summary.md").unlink(missing_ok=True)
    storage_service.delete_converted_artifacts(cid, uuid.UUID(file_id))

    details = f"Deleted: {', '.join(result.pages_deleted)}\n" if result.pages_deleted else ""
    if result.pages_updated:
        details += f"Updated: {', '.join(result.pages_updated)}\n"
    if result.dead_links_cleaned:
        details += f"Dead links cleaned: {result.dead_links_cleaned}\n"
    append_log(cid, "remove", filename, details)
    await mirror_to_disk(session, class_id, f"remove: {filename}")

    logger.info(
        "remove_complete",
        class_id=cid,
        filename=filename,
        pages_deleted=len(result.pages_deleted),
        pages_updated=len(result.pages_updated),
    )
    return result


async def _clean_dead_links(
    session: AsyncSession,
    class_id: uuid.UUID,
    pages: list[WikiPage],
    deleted_paths: list[str],
) -> int:
    """Unlink [[wiki-links]] to deleted pages in ``pages``. Returns links cleaned.

    Links name pages by slug, so a slug another remaining page still has is
    left alone.
    """
    if not deleted_paths:
        return 0
    deleted_slugs = {Path(p).stem for p in deleted_paths} - {Path(p.path).stem for p in pages}
    if not deleted_slugs:
        return 0

    cleaned = 0

    def _replace_dead_link(m: re.Match[str]) -> str:
        nonlocal cleaned
        slug = m.group(1).strip()
        if slug in deleted_slugs:
            cleaned += 1
            return (m.group(2) or slug).strip()
        return m.group(0)

    for page in pages:
        new_content = _WIKI_LINK.sub(_replace_dead_link, page.content)
        if new_content == page.content:
            continue
        page.content = new_content
        page.updated_at = datetime.now(UTC)
        await session.flush()
        await sync_fts_page(
            session,
            page_id=page.id,
            class_id=class_id,
            path=page.path,
            title=page.title,
            content=page_body(new_content),
        )
    return cleaned


async def handle_lint(
    session: AsyncSession,
    class_id: uuid.UUID,
) -> LintResult:
    """Audit the wiki for quality issues."""
    cid = str(class_id)
    all_pages = {
        p.path: p.content
        for p in await load_pages(session, class_id)
        if p.path.startswith("pages/")
    }
    if not all_pages:
        return LintResult(success=True, issues=[])

    issues: list[LintIssue] = []
    all_slugs = {Path(p).stem for p in all_pages}

    inbound_links: dict[str, int] = {slug: 0 for slug in all_slugs}

    # Citations name a source by filename or by file ID (see the wiki schema).
    existing_files_q = await session.execute(
        select(File.id, File.original_filename).where(File.class_id == class_id)
    )
    known_sources: set[str] = set()
    for file_id, filename in existing_files_q.all():
        known_sources.update({str(file_id), filename})

    for page_path, content in all_pages.items():
        for match in _WIKI_LINK.finditer(content):
            slug = match.group(1).strip()
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

        for match in _CITATION_FILE.finditer(content):
            cited_file = unquote(match.group(1))
            if cited_file not in known_sources:
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
        token_budget = int(_prompt_budget(LINT_SYSTEM_PROMPT) * 0.9)
        for page_path, content in list(all_pages.items())[:20]:
            tokens = _count_tokens(content)
            if tokens > token_budget:
                continue
            pages_for_llm.append(f"## {page_path}\n\n{content}")
            token_budget -= tokens

        if pages_for_llm:
            context = "\n\n---\n\n".join(pages_for_llm)
            user_prompt = f"## Wiki Pages to Audit\n\n{context}"
            try:
                async with _llm() as provider:
                    raw_output = await provider.complete(
                        LINT_SYSTEM_PROMPT, user_prompt, max_tokens=_output_budget()
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
            except (OSError, ValueError, RuntimeError, HypatiaError) as e:
                logger.warning("lint_llm_error", class_id=cid, error=str(e))

    append_log(cid, "lint", f"{len(issues)} issues found")
    return LintResult(success=True, issues=issues)


def _is_preserved(page: WikiPage) -> bool:
    """User-edited pages, and synthesis pages (built from other pages, so no
    source can regenerate them), survive a rebuild."""
    return page.user_edited or page.category == WikiCategory.SYNTHESIS


async def handle_rebuild_preview(
    session: AsyncSession,
    class_id: uuid.UUID,
) -> RebuildPreview:
    """Dry-run /rebuild: calculate what would change without making changes."""
    source_files_q = await session.execute(
        select(File).where(
            File.class_id == class_id,
            File.status.in_((FileStatus.READY, FileStatus.PROCESSING)),
        )
    )
    source_files = source_files_q.scalars().all()

    pages = [p for p in await load_pages(session, class_id) if p.path.startswith("pages/")]
    user_edited = sorted(p.path for p in pages if p.user_edited)
    synthesis = sorted(
        p.path for p in pages if not p.user_edited and p.category == WikiCategory.SYNTHESIS
    )
    to_delete = sorted(p.path for p in pages if not _is_preserved(p))

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
        pages_preserved_synthesis=synthesis,
    )


async def handle_rebuild(
    session: AsyncSession,
    class_id: uuid.UUID,
    *,
    task_id: str | None = None,
) -> RebuildResult:
    """Rebuild the wiki from source files.

    User-edited and synthesis pages are kept as they are. Every other page is
    regenerated; one the rebuilt wiki no longer contains is removed, unless its
    source failed to re-ingest (or the rebuild was cancelled first), in which
    case the old page is put back.
    """
    from app.services.ingestion_queue import get_ingestion_queue

    cid = str(class_id)

    # Files still queued would otherwise be ingested again by the queue on top
    # of the rebuilt wiki. One mid-ingestion finishes first: the lock below
    # waits for it.
    queued_q = await session.execute(
        select(File.id).where(
            File.class_id == class_id,
            File.status.in_((FileStatus.READY, FileStatus.PROCESSING)),
        )
    )
    queue = get_ingestion_queue()
    for file_id in queued_q.scalars().all():
        await queue.cancel_file(class_id, file_id)

    async with class_operation_lock(class_id):
        await session.execute(
            update(File)
            .where(File.class_id == class_id, File.status == FileStatus.PROCESSING)
            .values(status=FileStatus.READY)
        )
        await session.commit()
        session.expire_all()
        return await _rebuild(session, class_id, cid, task_id)


async def _rebuild(
    session: AsyncSession, class_id: uuid.UUID, cid: str, task_id: str | None
) -> RebuildResult:
    from app.services.task_manager import task_manager

    kept_paths: list[str] = []
    backups: list[_PageBackup] = []
    for row in await load_pages(session, class_id):
        if _is_preserved(row):
            kept_paths.append(row.path)
        else:
            backups.append(_PageBackup.capture(row))
    # Saved before the pages go, so a crash mid-rebuild can't lose them: the
    # next startup puts back any that the rebuild didn't regenerate.
    _write_rebuild_backup(cid, backups)
    for backup in backups:
        stale = await session.get(WikiPage, backup.id)
        if stale is not None:
            await _delete_page(session, stale)
    # The LLM should see the wiki as it now stands, not the pages just removed.
    await session.commit()

    source_files_q = await session.execute(
        select(File.id, File.original_filename).where(
            File.class_id == class_id, File.status == FileStatus.READY
        )
    )
    source_files = [(file_id, filename) for file_id, filename in source_files_q.all()]

    total = len(source_files)
    created_count = 0
    unfinished = {str(file_id) for file_id, _ in source_files}
    failed_sources: list[str] = []
    cancelled = False

    for i, (file_id, filename) in enumerate(source_files):
        if task_id and task_manager.is_cancelled(task_id):
            cancelled = True
            break

        if task_id:
            pct = int(i / total * 100) if total > 1 else None
            task_manager.update_progress(task_id, pct, f"Re-ingesting {filename} ({i + 1}/{total})")

        try:
            ingest_result = await ingest_source(session, class_id, file_id)
        except Exception as e:
            logger.exception("rebuild_ingest_error", class_id=cid, file=filename, error=str(e))
            await session.rollback()
            ingest_result = IngestResult(success=False, error=str(e))

        if ingest_result.success:
            unfinished.discard(str(file_id))
            created_count += len(ingest_result.pages_created) + len(ingest_result.pages_updated)
        else:
            failed_sources.append(f"{filename}: {ingest_result.error or 'unknown error'}")
            # Its previous pages are restored below, so it is not awaiting ingestion.
            await session.execute(
                update(File).where(File.id == file_id).values(status=FileStatus.READY)
            )
            await session.commit()

    known_ids = {str(file_id) for file_id, _ in source_files}
    present = {p.path for p in await load_pages(session, class_id)}
    restored: list[str] = []
    removed: list[str] = []
    for backup in backups:
        if backup.path in present:
            continue
        sources = set(backup.source_file_ids)
        # Pages whose sources are unknown are kept too while anything is unfinished.
        if sources & unfinished or (unfinished and not sources & known_ids):
            await _restore_page(session, class_id, backup)
            restored.append(backup.path)
        else:
            removed.append(backup.path)
    await session.commit()
    _rebuild_backup_path(cid).unlink(missing_ok=True)

    append_log(
        cid,
        "rebuild",
        f"{total} sources" + (" (cancelled)" if cancelled else ""),
        f"Created: {created_count}, Removed: {len(removed)}, Restored: {len(restored)}, "
        f"Preserved: {len(kept_paths)}\n",
    )
    await mirror_to_disk(
        session,
        class_id,
        "rebuild: cancelled (partial)" if cancelled else f"rebuild: {total} sources re-ingested",
    )

    return RebuildResult(
        success=not cancelled,
        pages_created=created_count,
        pages_deleted=len(removed),
        pages_preserved=len(kept_paths),
        error="Cancelled by user" if cancelled else None,
        pages_removed=removed,
        pages_restored=restored,
        failed_sources=failed_sources,
    )


@dataclass
class _PageBackup:
    """A page removed at the start of a rebuild, kept in case it must be put back."""

    id: uuid.UUID
    path: str
    content: str
    title: str
    category: WikiCategory
    source_file_ids: list[str]
    created_at: datetime | None

    @classmethod
    def capture(cls, row: WikiPage) -> _PageBackup:
        return cls(
            id=row.id,
            path=row.path,
            content=row.content,
            title=row.title,
            category=row.category,
            source_file_ids=[str(s) for s in row.source_file_ids or []],
            created_at=row.created_at,
        )


def _rebuild_backup_path(cid: str) -> Path:
    return storage_service.class_dir(cid) / ".rebuild-backup.json"


def _write_rebuild_backup(cid: str, backups: list[_PageBackup]) -> None:
    payload = [
        {
            "id": str(b.id),
            "path": b.path,
            "content": b.content,
            "title": b.title,
            "category": b.category.value,
            "source_file_ids": b.source_file_ids,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in backups
    ]
    path = _rebuild_backup_path(cid)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


async def recover_interrupted_rebuilds(session: AsyncSession) -> list[str]:
    """Put back pages a crashed /rebuild deleted but never regenerated.

    Runs at startup. Returns the ids of the Classes recovered.
    """
    recovered: list[str] = []
    classes_root = storage_service.class_dir("x").parent
    if not classes_root.exists():
        return recovered
    for backup_file in classes_root.glob("*/.rebuild-backup.json"):
        cid = backup_file.parent.name
        try:
            class_id = uuid.UUID(cid)
            entries = json.loads(backup_file.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            logger.warning("rebuild_backup_unreadable", path=str(backup_file))
            continue
        present = {p.path for p in await load_pages(session, class_id)}
        restored = 0
        for entry in entries:
            if entry["path"] in present:
                continue
            await _restore_page(
                session,
                class_id,
                _PageBackup(
                    id=uuid.UUID(entry["id"]),
                    path=entry["path"],
                    content=entry["content"],
                    title=entry["title"],
                    category=WikiCategory(entry["category"]),
                    source_file_ids=list(entry["source_file_ids"]),
                    created_at=datetime.fromisoformat(entry["created_at"])
                    if entry["created_at"]
                    else None,
                ),
            )
            restored += 1
        await session.commit()
        backup_file.unlink(missing_ok=True)
        if restored:
            append_log(
                cid, "rebuild", "recovered after an interrupted rebuild", f"Restored: {restored}\n"
            )
            await mirror_to_disk(session, class_id, "rebuild: recover interrupted rebuild")
        logger.info("rebuild_recovered", class_id=cid, restored=restored)
        recovered.append(cid)
    return recovered


async def index_page_for_search(session: AsyncSession, row: WikiPage) -> None:
    """(Re)build a stored page's full-text and embedding entries from its text."""
    parsed = parse_page_document(row.path, row.content)
    body = parsed.content if parsed else page_body(row.content)
    await sync_fts_page(
        session,
        page_id=row.id,
        class_id=row.class_id,
        path=row.path,
        title=row.title,
        content=body,
        tags=parsed.tags if parsed else None,
    )
    await _upsert_embedding_safe(session, row.id, body)


async def _restore_page(session: AsyncSession, class_id: uuid.UUID, backup: _PageBackup) -> None:
    row = WikiPage(
        id=backup.id,
        class_id=class_id,
        path=backup.path,
        title=backup.title,
        category=backup.category,
        content=backup.content,
        source_file_ids=backup.source_file_ids,
    )
    if backup.created_at is not None:
        row.created_at = backup.created_at
    session.add(row)
    await session.flush()
    await index_page_for_search(session, row)


async def revert_wiki(session: AsyncSession, class_id: uuid.UUID, commit_sha: str) -> bool:
    """Make the wiki's pages what they were at ``commit_sha`` of its git history.

    The pages are loaded into the database (the source of truth), which is
    then mirrored back to disk as a new commit, so history is preserved.
    Returns False if that commit's pages can't be read.
    """
    async with class_operation_lock(class_id):
        snapshot = read_pages_at(str(class_id), commit_sha)
        if snapshot is None:
            return False

        current = {p.path: p for p in await load_pages(session, class_id)}
        for path, row in current.items():
            if path.startswith("pages/") and path not in snapshot:
                await _delete_page(session, row)

        for path, document in snapshot.items():
            parsed = parse_page_document(path, document) or ParsedWikiPage(
                path=path, title=Path(path).stem, content=page_body(document)
            )
            row = await _store_page(
                session,
                class_id,
                current.get(path),
                parsed,
                document,
                source_ids=parsed.sources,
                replace_sources=True,
            )
            row.user_edited = parsed.user_edited
        await session.commit()

        append_log(str(class_id), "revert", commit_sha[:8])
        await mirror_to_disk(session, class_id, f"Revert to {commit_sha[:8]}")
        return True


# ---------------------------------------------------------------------------
# Streaming support (Task 3B.13)
# ---------------------------------------------------------------------------


#: Share of the /ask budget earlier conversation turns may take.
_ASK_HISTORY_RATIO = 0.1


async def handle_ask_stream(
    session: AsyncSession,
    class_id: uuid.UUID,
    query: str,
    *,
    history: list[tuple[str, str]] | None = None,
    consulted: list[str] | None = None,
) -> AsyncIterator[str]:
    """Stream an /ask response token-by-token.

    ``history`` is the recent conversation as (role, text), oldest first, so a
    follow-up like "what about the second one?" can be answered; the previous
    question also steers the page search. ``consulted`` is filled with the
    paths of the pages the answer was based on.
    """
    cid = str(class_id)
    history = history or []
    previous_question = next((text for role, text in reversed(history) if role == "user"), "")
    pages_context, pages_consulted = await _ask_context(
        session,
        class_id,
        query,
        search_text=f"{previous_question} {query}".strip() if previous_question else None,
    )
    if consulted is not None:
        consulted.extend(pages_consulted)

    # The chat router records the question and the streamed answer in history.
    if not pages_consulted:
        yield _NO_PAGES_ANSWER
        return

    context_block = "---\n".join(pages_context)
    conversation = _format_history(
        history, int(_prompt_budget(ASK_SYSTEM_PROMPT) * _ASK_HISTORY_RATIO)
    )
    user_prompt = (
        f"## Context\n\n{context_block}\n\n---\n\n"
        + (f"## Earlier in this conversation\n\n{conversation}\n\n---\n\n" if conversation else "")
        + f"## Question\n\n{query}"
    )

    try:
        async with _llm() as provider:
            async for chunk in provider.stream(
                ASK_SYSTEM_PROMPT, user_prompt, max_tokens=_output_budget()
            ):
                yield chunk
    except (OSError, ValueError, RuntimeError, HypatiaError) as e:
        logger.error("ask_stream_error", class_id=cid, error=str(e))
        yield f"\n\n[Error: {e}]"
