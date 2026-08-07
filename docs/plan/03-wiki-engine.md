# Phase 3: Wiki Engine

**Goal**: Implement the core LLM Wiki pattern — the service that reads converted source material and builds/maintains a persistent, interlinked wiki of markdown pages per Class. Split into two sub-phases: **3A** gets a minimal end-to-end pipeline working (ingest + /ask), and **3B** adds the remaining commands, user edits, and polish.

**Prerequisites**: Phase 2 (file processing pipeline produces markdown from source files).

**Outputs**: Given a converted source file, the wiki engine generates wiki pages (summary, concepts, entities), maintains an index and log, supports querying with citations, and preserves user-edited content.

---

## Phase 3A: Wiki Engine Spike

**Goal**: Get a single source ingestion + /ask query working end-to-end. This is the minimum viable wiki engine — enough to prove the pattern works and unblock frontend integration (Phase 4 can expose these endpoints while 3B continues).

**Prerequisites**: Phase 2 (file conversion produces markdown).

---

### 3A.1 Implement LLM service abstraction
Create `app/services/llm_service.py` and `app/services/llm_providers/`:
- Define an abstract `LLMProvider` interface:
  ```python
  class LLMProvider(ABC):
      async def complete(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str: ...
      async def stream(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]: ...
  ```
- Implement concrete providers:
  - `AnthropicProvider` — uses `anthropic` SDK (Claude). **This is the default provider.**
  - `OpenAIProvider` — uses `openai` SDK (GPT-4o, GPT-4o-mini)
  - `OllamaProvider` — uses `httpx` to call local Ollama API
  - `CopilotProvider` — uses GitHub Copilot API
- Factory function: `get_llm_provider(config) -> LLMProvider`
- Configuration via `app/config.py`: provider name (default: `anthropic`), model name, API key, base URL.

**Acceptance**: Can send a prompt and receive a response from all four providers. Streaming works. Default is Claude.

---

### 3A.2 Design wiki schema template
Create the default `schema.md` template that gets placed in each Class's `wiki/` directory:
- Defines page categories: source-summaries, concepts, entities, synthesis.
- Defines frontmatter conventions:
  ```yaml
  ---
  title: "Page Title"
  type: source-summary | concept | entity | synthesis
  sources: [file-id-1, file-id-2]  # Which source files contributed
  created: 2026-08-05
  updated: 2026-08-05
  tags: [tag1, tag2]
  user_edited: false
  ---
  ```
- Defines linking conventions: `[[page-name]]` style wiki links.
- Defines citation format: `[claim text](hypatia://cite?file=filename&loc=page3)` or `[claim text](hypatia://cite?file=lecture.mp4&t=145)`.
- Instructions for the LLM on how to create, update, and cross-reference pages.

**Acceptance**: Schema template is clear enough that an LLM can follow it to produce consistent wiki pages.

---

### 3A.3 Implement citation injection
Create `app/services/citation_service.py`:
- When the LLM generates wiki content from a source, every factual claim should include a citation link.
- Citation format for documents:
  ```markdown
  Neural networks use backpropagation for training [source](hypatia://cite?file=chapter-3-notes.pdf&page=5)
  ```
- Citation format for videos:
  ```markdown
  The professor explains gradient descent [source](hypatia://cite?file=lecture-1.mp4&t=342)
  ```
- The LLM prompt must instruct it to include these citations.
- `generate_citation_uri(file_id, location)` — creates the `hypatia://` URI.
- `parse_citation_uri(uri)` — extracts file and location for the frontend to handle.
- Location types: `page` (PDF page), `section` (heading), `line` (line number), `t` (timestamp in seconds).

**Acceptance**: Wiki pages contain citation links. Links can be parsed back into file + location.

---

### 3A.4 Implement LLM output parsing
In `app/services/wiki_parser.py`:
- The LLM will return structured output indicating which pages to create/update.
- Define a response format using XML-tagged blocks:
  ```
  <wiki-page path="pages/source-summaries/lecture-1.md">
  ---
  title: "Lecture 1: Intro to Neural Networks"
  ...
  ---
  # Content here...
  </wiki-page>

  <wiki-page path="pages/concepts/neural-networks.md" action="update">
  ...
  </wiki-page>
  ```
- Parse this output to extract individual page contents.
- Apply creates and updates to the filesystem and database.
- Handle parse failures gracefully (log the raw output, retry once, then report error).

**Acceptance**: LLM output is reliably parsed into discrete page operations.

---

### 3A.5 Implement source ingestion workflow
Create the core ingestion pipeline in `app/services/wiki_engine.py`:
- `ingest_source(class_id, file_id) -> IngestResult`:
  1. Read the converted markdown file for this source.
  2. Read the current wiki schema, index, and relevant existing pages.
  3. **Context budget allocation** (see architectural decision #16):
     - Always include: schema (~500 tokens) + index (~1000 tokens) = ~10% of context.
     - Source content: up to ~50% of context window. If the source exceeds this, chunk it (see below).
     - Existing related pages (found via FTS5): up to ~30% of context. Select top-N pages by relevance until budget is filled.
     - Reserve ~10% for LLM output.
     - Use `tiktoken` (or provider-specific tokenizer) to count tokens before sending.
  4. Prompt the LLM to:
     a. Write a source-summary page for this file.
     b. Identify key concepts and entities mentioned.
     c. For each concept/entity: create a new page or update an existing one.
     d. Update cross-references between pages.
  5. Parse the LLM output (Task 3A.4).
  6. Write all generated/updated pages to the wiki directory.
  7. Update `index.md` with new/modified pages.
  8. Append an entry to `log.md`.
  9. Update `wiki_pages` table in the database.
  10. Auto-commit wiki changes via git (Task 1.11).
- **Chunking strategy for large sources**: If source exceeds ~50% of context budget:
  - Split by headings or every ~3000 words.
  - Process chunks sequentially: first chunk creates pages, subsequent chunks update them.
  - Each chunk includes a summary of what previous chunks produced (from the index).
- The LLM should receive the schema as a system prompt and the source content as user input.

**Acceptance**: Ingesting a source file produces a source-summary page, relevant concept/entity pages, updates the index, and creates a git commit. Large sources are chunked correctly.

---

### 3A.6 Implement minimal search for wiki context
Create a basic search capability in `app/services/wiki_search.py` that the wiki engine uses internally:
- Set up the FTS5 virtual table for wiki pages (pulled forward from Phase 7):
  ```sql
  CREATE VIRTUAL TABLE wiki_pages_fts USING fts5(
      title, content, tags,
      content='wiki_pages', content_rowid='rowid'
  );
  ```
- `search_wiki_pages(class_id, query, limit=10) -> list[WikiPageSummary]` — BM25 ranked text search.
- Keep FTS5 index in sync: update on page create/update/delete.
- This is used by `/ask` (Task 3A.7) to find relevant context pages, and by ingestion to find related existing pages.
- The full search UI and advanced features remain in Phase 7.

**Acceptance**: Can search wiki pages by keyword. Results are ranked by relevance. Index stays in sync with page changes.

---

### 3A.7 Implement /ask command handler
In `app/services/wiki_engine.py`:
- `handle_ask(class_id, query) -> AsyncIterator[str]`:
  1. Search wiki pages using FTS5 (Task 3A.6) to find relevant pages.
  2. **Context budget for /ask**: Select top pages by FTS5 rank, filling up to ~70% of context window. Always include the index for orientation. Reserve ~20% for LLM response.
  3. Read the content of selected pages (typically 5-10, fewer if pages are large).
  4. Prompt the LLM with the query and the relevant page content as context.
  5. Stream the response back with citations.
  6. Save the query and response to `chat_messages` table.
- The LLM must cite specific wiki pages and, through them, original sources.
- Response should be markdown with inline citations.

**Acceptance**: `/ask "What is backpropagation?"` returns a cited answer drawn from wiki pages.

---

### 3A Sequencing

```
3A.1 (LLM service) ──→ 3A.5 (ingest)
3A.2 (schema)      ──→ 3A.5 (ingest)
3A.3 (citations)   ──→ 3A.5 (ingest)
3A.4 (parsing)     ──→ 3A.5 (ingest)
3A.6 (minimal search) ──→ 3A.5 (ingest) + 3A.7 (/ask)
3A.5 (ingest) ──→ 3A.7 (/ask)
3A.8 (ingestion queue) ← wraps 3A.5, can be built after it
```

- 3A.1-3A.4 and 3A.6 can be built in parallel (they're all inputs to 3A.5).
- 3A.5 (ingest) is the core — it integrates everything.
- 3A.7 (/ask) depends on 3A.5 (needs pages to exist) and 3A.6 (needs search).
- 3A.8 (queue) wraps 3A.5 — build after ingest works for a single file.

**Exit criterion for 3A**: Can upload a PDF, have it ingested into wiki pages, and then `/ask` a question that gets a cited answer. This unblocks Phase 4 API development.

---

### 3A.8 Implement ingestion queue
Create `app/services/ingestion_queue.py` to manage concurrent file processing:
- `enqueue_ingestion(class_id, file_id)` — adds a file to the processing queue.
- Queue processes files **one at a time** per Class (prevents LLM rate limit issues and ensures wiki consistency).
- Multiple Classes can process in parallel (they're independent).
- Queue state:
  - `pending` — waiting in queue, shows queue position.
  - `processing` — currently being ingested.
  - `complete` — done.
  - `failed` — error occurred (stored for display).
- Frontend polls file status and shows queue position: "Processing (2 of 5)".
- If the backend restarts, pending items are re-queued from the database (files with `status: "pending"`).
- Respects LLM provider rate limits: if rate-limited, back off and retry with exponential delay.
- Prevents double-ingestion: check if a file is already queued/processing before adding.

**Acceptance**: Multiple file uploads are queued and processed sequentially. Queue position is visible. Rate limits are handled gracefully.

---

## Phase 3B: Wiki Engine Full

**Goal**: Add remaining commands (/summarize, /remove, /lint, /rebuild, /export), user edit tracking, wiki page CRUD, and prompt regression testing.

**Prerequisites**: Phase 3A (basic ingestion + /ask working).

---

### 3B.1 Implement index and log management
In `app/services/wiki_engine.py`:
- `rebuild_index(class_id)` — regenerates `index.md` by scanning all wiki pages:
  ```markdown
  # Wiki Index

  ## Source Summaries
  - [Lecture 1](pages/source-summaries/lecture-1.md) — Introduction to neural networks (2 concepts linked)
  - [Chapter 3 Notes](pages/source-summaries/chapter-3-notes.md) — Backpropagation deep dive

  ## Concepts
  - [Neural Networks](pages/concepts/neural-networks.md) — 3 sources
  - [Backpropagation](pages/concepts/backpropagation.md) — 2 sources

  ## Entities
  - [Geoffrey Hinton](pages/entities/geoffrey-hinton.md) — 1 source
  ```
- `append_log(class_id, action, details)` — adds a timestamped entry to `log.md`:
  ```markdown
  ## [2026-08-05T14:23:00] ingest | lecture-1.mp4
  Created source summary. Added concepts: neural-networks, backpropagation. Updated entity: geoffrey-hinton.
  ```

**Acceptance**: Index accurately reflects all wiki pages. Log records all operations chronologically.

---

### 3B.2 Implement /summarize command handler
In `app/services/wiki_engine.py`:
- `handle_summarize(class_id, topic) -> str`:
  1. Search the wiki for all pages relevant to the topic (using FTS5).
  2. Read the content of relevant pages.
  3. Prompt the LLM to synthesize a comprehensive summary page.
  4. Write the summary as a new wiki page in `pages/` (category: synthesis).
  5. Update `index.md` and `log.md`.
  6. Update the database.
  7. Auto-commit via git.
- The generated page should cross-reference existing pages and cite original sources.

**Acceptance**: `/summarize "gradient descent"` produces a new wiki page that synthesizes information from multiple sources and is added to the wiki.

---

### 3B.3 Implement /remove command handler
In `app/services/wiki_engine.py`:
- `handle_remove(class_id, file_path) -> RemoveResult`:
  1. Identify the file to remove (match by filename or path).
  2. Delete the original file from `raw/`.
  3. Delete the converted file from `converted/`.
  4. Delete the source-summary wiki page for this file.
  5. For concept/entity pages that reference this source:
     - If the page has OTHER sources too: strip this source's references from frontmatter and content, keep the page.
     - If this was the ONLY source: delete the page entirely.
  6. Rebuild `index.md` (remove deleted pages, update counts).
  7. Append removal to `log.md`.
  8. Scan all remaining wiki pages for dead `[[links]]` to deleted pages and remove or flag them.
  9. Delete the file record from the database.
  10. Delete associated wiki_page records.
  11. Auto-commit via git.

**Acceptance**: Removing a file cleans up all associated wiki pages, references, and database records without leaving orphans.

---

### 3B.4 Implement /lint command handler
In `app/services/wiki_engine.py`:
- `handle_lint(class_id) -> LintResult`:
  1. Scan all wiki pages for issues:
     - **Contradictions**: pages that make conflicting claims about the same topic.
     - **Orphan pages**: pages with no inbound links from other pages.
     - **Broken links**: `[[wiki-links]]` that point to non-existent pages.
     - **Stale pages**: pages whose source files have been updated but the wiki page hasn't been regenerated.
     - **Missing pages**: important concepts mentioned in multiple pages but lacking their own dedicated page.
     - **Dead citations**: `hypatia://cite` links pointing to files that no longer exist.
  2. Use the LLM to assess contradictions and suggest missing pages.
  3. Return a structured report with issues grouped by severity (error, warning, suggestion).
  4. Append lint results to `log.md`.

**Acceptance**: `/lint` produces a structured report identifying wiki health issues. Actionable suggestions are provided.

---

### 3B.5 Implement /rebuild command handler
In `app/services/wiki_engine.py`:
- `handle_rebuild(class_id, dry_run=False) -> RebuildResult`:
  1. **Cost estimation**: Before starting, calculate estimated token usage:
     - Count total tokens across all source files.
     - Estimate output tokens (~1.5x source for wiki generation).
     - Display estimate to user: "This will process ~45,000 tokens across 8 files. Estimated cost: ~$2.50 (Claude Sonnet)."
     - Require user confirmation before proceeding.
  2. **Dry-run / preview mode** (`dry_run=True`):
     - Run the full analysis phase (identify pages to create, update, or delete) without writing any changes.
     - Return a structured preview: `{"pages_to_create": [...], "pages_to_delete": [...], "pages_to_update": [...], "pages_preserved_user_edited": [...], "estimated_cost": "...", "estimated_time": "..."}`.
     - Frontend shows this as a diff-like view: green (new), red (removed), yellow (updated), grey (preserved).
     - User can then confirm to execute, or cancel. The dry-run output is cheap (no LLM calls for generation, only token counting and file scanning).
  3. Read all source files currently in the Class.
  4. Identify user-edited wiki pages (those with `user_edited: true` in frontmatter).
  5. **Skip user-edited pages entirely** — do not regenerate or modify them.
  6. Delete all non-user-edited LLM-generated wiki pages.
  7. Re-ingest every source file using the current LLM and prompts (via ingestion queue).
  8. Rebuild `index.md` and append rebuild entry to `log.md`.
  9. Auto-commit via git (allows revert if rebuild is bad).
  10. Run as a long-running background task with progress reporting.
- **Provider switching note**: If the user changes LLM provider in settings, recommend a `/rebuild` to regenerate with the new model. Surface this as a suggestion, not a requirement.
- **Cost guardrail**: If estimated cost exceeds a configurable threshold (default: $10), require explicit confirmation with the estimate shown prominently.
- The dry-run preview is the default UX: `/rebuild` always shows the preview first, then asks for confirmation. `/rebuild --force` skips the preview (for scripts/automation).

**Acceptance**: `/rebuild` shows a preview of what will change (pages created/deleted/updated) and cost estimate before executing. Regenerates the entire wiki from scratch on confirmation. User-edited pages are preserved untouched. Progress is reported. Git commit enables revert.

---

### 3B.6 Implement /export command handler
In `app/services/wiki_engine.py`:
- `handle_export(class_id, format="zip") -> ExportResult`:
  1. Collect all wiki pages (markdown files).
  2. Package into the requested format:
     - `zip` — a ZIP archive of all wiki markdown files, preserving directory structure.
     - Future formats: PDF compilation, HTML static site.
  3. Return the path to the generated export file for download.
  4. Append export entry to `log.md`.

**Acceptance**: `/export` produces a downloadable ZIP of the wiki. Directory structure is preserved.

---

### 3B.7 Implement wiki page CRUD operations
In `app/services/wiki_engine.py`:
- `get_wiki_tree(class_id) -> WikiTree` — returns the hierarchical structure of all wiki pages for the sidebar.
- `get_wiki_page(class_id, page_path) -> WikiPage` — reads a specific page's content.
- `get_wiki_context(class_id) -> str` — returns schema + index for LLM prompting.
- `update_wiki_page(class_id, page_path, content, is_user_edit=False)` — saves a page, optionally marking as user-edited.

**Acceptance**: Can list, read, and edit wiki pages. Tree structure matches the directory layout.

---

### 3B.8 Implement user edit tracking
Enable users to manually edit wiki pages while preserving their edits across LLM rebuilds:
- **Strategy: skip-on-rebuild** (simplified from merge-based approach):
  - When a user edits a page: set `user_edited: true` in the page's frontmatter.
  - During `/rebuild`: skip all pages with `user_edited: true`. Do not regenerate, merge, or modify them.
  - During `/ingest` of a new source: if the LLM wants to update a user-edited page, create a separate "suggested update" note in `log.md` instead of modifying the page.
  - User can manually un-mark a page (remove `user_edited` flag) to opt back into LLM generation.
- Show a visual indicator on user-edited pages in the UI (badge in sidebar tree).
- Auto-commit user edits via git with message `"user-edit: modified {page_path}"`.

**Acceptance**: User can edit a wiki page. After `/rebuild`, user-edited pages are preserved untouched. User can opt back in to LLM generation.

---

### 3B.9 Design and write LLM prompts
Create a prompts module at `app/services/prompts/`:
- `ingest_prompt.py` — system prompt for source ingestion (instructs LLM on wiki conventions, page formats, citation requirements).
- `query_prompt.py` — system prompt for /ask queries (instructs LLM on how to search, cite, and respond).
- `summarize_prompt.py` — system prompt for /summarize (instructs LLM on synthesis and cross-referencing).
- `lint_prompt.py` — system prompt for /lint (instructs LLM on contradiction detection and health assessment).
- Prompts should include the wiki schema as context.
- Prompts should be testable and iterable — expect refinement over time.

**Acceptance**: Prompts are well-structured, produce consistent wiki output, and correctly instruct the LLM on citation format.

---

### 3B.10 Implement prompt regression testing
Create a test corpus and harness for detecting prompt quality regressions:
- Create `tests/golden/` directory with:
  - 3-5 sample source documents (short excerpts covering different types: PDF text, transcript, slides).
  - Expected wiki output for each (the "golden" reference — manually verified as good).
- Create `tests/test_prompt_regression.py`:
  - For each golden input: run through the real LLM (or a deterministic mock), parse output.
  - Assert structural correctness: frontmatter present, citations valid, cross-references resolve, page categories correct.
  - Do NOT assert exact text match (LLM output varies). Assert structural properties.
  - Track: number of pages generated, citation count, link validity, frontmatter completeness.
- Run as part of CI (with mock LLM for speed) and periodically with real LLM (for quality).
- When prompts change: re-run against golden corpus, review diffs, update golden references if improved.

**Acceptance**: Prompt changes that break structural output are caught automatically. Golden corpus covers all page types.

---

### 3B.11 Write tests for wiki engine
- Test ingestion with mock LLM (deterministic responses).
- Test /ask, /summarize, /remove, /lint, /rebuild, /export workflows.
- Test index and log generation.
- Test citation generation and parsing.
- Test /remove cleanup (orphan detection, reference stripping).
- Test user edit preservation (skip-on-rebuild behavior).
- Test error handling (LLM timeout, malformed output, parse failure).
- Test git auto-commit (verify commits are created, can be reverted).

**Acceptance**: All wiki engine operations are tested with mock LLM responses.

---

### 3B.12 Implement long-running operation support
Add infrastructure for operations that take significant time (/rebuild, /lint, large ingests):
- Create `app/services/task_manager.py`:
  - `start_task(operation, class_id) -> task_id` — registers a background task.
  - `update_progress(task_id, percent, message)` — updates progress.
  - `cancel_task(task_id)` — sets cancellation flag (operation checks periodically).
  - `get_task_status(task_id) -> TaskStatus` — returns current state.
- Operations check `is_cancelled()` between steps and abort cleanly if true.
- Progress is reported via WebSocket events (defined in API contract, Task 1.10):
  ```json
  {"type": "progress", "task_id": "...", "operation": "rebuild", "percent": 45, "message": "Processing page 3/7..."}
  ```
- On cancellation: roll back partial changes (git revert to pre-operation commit).

**Acceptance**: Long operations report progress. Can be cancelled mid-operation. Partial changes are rolled back on cancel.

---

## 3B Sequencing

```
3B.1 (index/log) — can refine what 3A started
3B.9 (prompts) — refine prompts from 3A
3B.2 (/summarize) ← depends on 3B.1
3B.3 (/remove)    ← depends on 3B.1
3B.4 (/lint)      ← depends on 3B.9
3B.5 (/rebuild)   ← depends on 3B.8 (user edits) + 3B.12 (task manager)
3B.6 (/export)    — independent
3B.7 (CRUD)       — independent, can start immediately
3B.8 (user edits) ← depends on 3B.7
3B.10 (prompt testing) ← depends on 3B.9
3B.11 (tests)     — after all above
3B.12 (task manager) — early, used by /rebuild and /lint
```

- 3B.7 (CRUD) and 3B.12 (task manager) can start immediately.
- 3B.1 and 3B.9 refine work from 3A.
- 3B.2, 3B.3, 3B.4, 3B.6 can be built in parallel after 3B.1/3B.9.
- 3B.5 (/rebuild) depends on 3B.8 + 3B.12.
- 3B.10 and 3B.11 are last.

---

## Risks

| Risk | Mitigation |
|------|------------|
| LLM produces inconsistent page formats | Strong prompt engineering. Parse-and-validate output before writing. Prompt regression tests (3B.10) catch regressions. |
| LLM hallucinates citations | Validate that cited files/timestamps exist before writing. |
| Large source files exceed LLM context window | Chunk the source, ingest chunks sequentially, merge results. |
| /remove leaves orphan references | Implement a link-checking pass after removal. /lint detects orphans. |
| Wiki pages get out of sync with database | Make filesystem the source of truth; database is a cache that can be rebuilt. Git history provides an additional safety net. |
| Provider switch produces different quality output | Recommend /rebuild after provider change. Prompt regression tests verify structural consistency across providers. |
