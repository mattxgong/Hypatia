# Phase 7: Search & Retrieval + Deferred UX Improvements

**Goal**: Upgrade from basic FTS5 keyword search (implemented in Phase 3A) to a full hybrid retrieval system (BM25 + semantic embeddings), enrich the search UI with categories and filters, and deliver the UX improvements deferred from Phase 6 (source viewer media support, drag-and-drop upload, upload progress).

**Prerequisites**: Phase 3A (FTS5 search), Phase 4 (search API endpoint), Phase 6 (frontend connected to backend).

**Outputs**: A fast, accurate hybrid search system; a rich source viewer with native media playback; drag-and-drop file upload with progress tracking.

---

## What's Already Implemented (from Phase 3A/6)

These were delivered early and do **not** need to be re-done:
- FTS5 virtual table created at startup (`wiki_search.py:ensure_fts_index`)
- `search_wiki_pages()` function with BM25 ranking and snippet generation
- `GET /api/classes/{class_id}/wiki/search?q=...` endpoint (returns up to 20 results)
- `handle_ask` uses `search_wiki_pages()` for context retrieval (10 results, token-budgeted)
- Frontend: debounced search bar (300ms), `searchResultsProvider`, result list with title+snippet, click-to-navigate
- API client `searchWiki()` method
- API client `uploadFiles()` already accepts an `onProgress` callback (wired to Dio `onSendProgress`)

---

## Tasks

### 7.1 Add category filtering and pagination to search API
Extend `app/services/wiki_search.py` and `app/routers/wiki.py`:
- Add `category: str | None` parameter to `search_wiki_pages()` — join with `wiki_pages` to filter by `category` column.
- Add `offset: int = 0` parameter for pagination.
- Return `category` field in each result (requires join with the `wiki_pages` table by `page_id`).
- Update the router signature: `GET /api/classes/{class_id}/wiki/search?q=...&category=...&offset=0&limit=20`
- Wrap response in a schema that includes `total_count` alongside the result list for frontend pagination.

**Acceptance**: Can filter search by category (source-summary, concept, entity, synthesis). Pagination works. Total count is returned.

---

### 7.2 Implement semantic search with sentence-transformers
Create `app/services/embedding_service.py`:
- Use `sentence-transformers` with the `all-MiniLM-L6-v2` model (22M params, ~90MB download, fast on CPU).
- New table `wiki_page_embeddings` (Alembic migration):
  - `id` (PK), `page_id` (FK → wiki_pages.id, unique), `embedding` (BLOB — numpy float32 bytes, 384 dims = 1536 bytes).
- Functions:
  - `generate_embedding(text: str) -> bytes` — encode text, return float32 bytes.
  - `upsert_embedding(session, page_id, content: str)` — generate and store/replace embedding.
  - `delete_embedding(session, page_id)` — remove embedding on page deletion.
  - `search_semantic(session, class_id, query: str, limit=10) -> list[SemanticSearchResult]` — embed query, cosine similarity against stored vectors, return ranked results with page_id, score.
- **Lazy model loading**: The `SentenceTransformer` model is loaded on first call, not at import or startup. Cached in a module-level variable.
- **Optional dependency**: If `sentence-transformers` is not installed, the module raises a clear error only when called, and the hybrid search (7.3) falls back to FTS5-only.

Integration into existing code:
- `wiki_engine.py` — after every page create/update disk write, call `upsert_embedding()`.
- `wiki_engine.py` — inside `handle_remove()`, call `delete_embedding()` for removed pages.
- `pyproject.toml` — add `sentence-transformers>=2.2.0` as an optional dependency group (`[project.optional-dependencies] semantic = [...]`).

**Acceptance**: Embeddings generated on page create/update. `search_semantic()` finds conceptually related pages even without keyword overlap.

---

### 7.3 Implement hybrid search (BM25 + semantic fusion)
Update `app/services/wiki_search.py`:
- New function `hybrid_search(session, class_id, query, limit=20, category=None, offset=0, mode="hybrid")`:
  - `mode="keyword"` → FTS5 only (existing behavior).
  - `mode="semantic"` → embedding only.
  - `mode="hybrid"` (default) → both, combined via Reciprocal Rank Fusion (RRF): `score(d) = Σ 1/(k + rank_i(d))` with k=60.
  - Deduplicates by `page_id`, keeps the higher fused score.
  - Applies category filter and offset/limit after fusion.
- Fallback: if embedding service raises `ImportError` (sentence-transformers not installed) or any other error, log a warning and return FTS5 results only.
- Update the router to call `hybrid_search()` and expose the `mode` query parameter.

**Acceptance**: Hybrid search returns results from both retrieval methods. Graceful fallback when embeddings unavailable.

---

### 7.4 Upgrade /ask context retrieval to use hybrid search
Update `app/services/wiki_engine.py`:
- In `handle_ask()` (line ~274) and `handle_ask_stream()` (line ~1366): replace the call to `search_wiki_pages(session, class_id, query, limit=10)` with `hybrid_search(session, class_id, query, limit=10)`.
- One-line import + function call change.

**Acceptance**: /ask queries benefit from semantic retrieval. Conceptual questions ("how do neural networks relate to backpropagation?") get better context even if those exact words aren't in the wiki page titles.

---

### 7.5 Enrich frontend search UI
Update `frontend/lib/widgets/sidebar/search_bar.dart` and create `frontend/lib/providers/search_provider.dart`:
- Extract search providers out of the widget file into a dedicated provider file.
- Add category filter chips above results: All | Concepts | Entities | Sources | Synthesis.
- Show a category badge/chip on each search result.
- Show highlighted snippet text (bold matched terms).
- Add a "No results" empty state with search suggestions.
- Add a search mode selector (keyword / semantic / hybrid) — small dropdown or segmented control below the search input.
- Update `WikiSearchResult` model to include `category` field.

**Acceptance**: Search UI shows category filters, category badges on results, and rich snippets. Mode selector works.

---

### 7.6 Implement upload progress UI
Update `frontend/lib/widgets/sidebar/add_file_button.dart`:
- Create a new `UploadProgressNotifier` (or `StateNotifierProvider`) to manage upload state:
  - States: idle, uploading (file name, progress 0.0–1.0, files done/total), complete, error.
- Wire the existing `onProgress` callback from `api_client.dart` into the notifier.
- Render an inline progress indicator below the "Add Files" button:
  - Shows file name, progress bar with percentage, "X of Y files" counter.
  - Cancel button (cancels the Dio request via `CancelToken`).
- On completion: show success snackbar, return to idle state.
- On error: show error with retry option.

**Acceptance**: Upload shows real-time progress percentage. Multi-file uploads show aggregate and per-file state. Cancel works.

---

### 7.7 Add drag-and-drop file upload
Add `desktop_drop` package and integrate:
- Add `desktop_drop: ^0.6.0` to `pubspec.yaml`.
- Wrap the `HomeScreen` scaffold body in a `DropTarget` widget.
- On hover: show a semi-transparent overlay with "Drop files to upload" text and an upload icon.
- On drop: validate file extensions (same allowed list as file picker). Reject unsupported types with a snackbar.
- Trigger the same upload flow as the "Add Files" button (including progress UI from 7.6).
- Requires a class to be selected — if no class, show "Select a class first" message.

**Acceptance**: Dragging files onto the app window shows an overlay. Dropping valid files starts the upload with progress. Invalid files are rejected.

---

### 7.8 Upgrade source viewer with media support
Enhance `frontend/lib/widgets/source_viewer/source_viewer.dart`:
- Add packages to `pubspec.yaml`:
  - `media_kit: ^1.1.10` + `media_kit_video: ^1.1.10` + `media_kit_libs_windows: ^1.0.9`
  - `pdfrx: ^1.0.0`
- Initialize `MediaKit.ensureInitialized()` in `main.dart`.
- Detect file type from the `SourceFile.fileType` field and render the appropriate viewer:
  - **video / audio**: `media_kit` `Video` widget. Parse `loc` as seconds, seek on open.
  - **pdf**: `pdfrx` `PdfViewer` widget. Parse `loc` as page number, jump on open.
  - **image** (png, jpg, gif): `InteractiveViewer` wrapping `Image.network(rawUrl)` for zoom/pan.
  - **text / markdown / other**: Current monospace `SelectableText` (no change). Attempt to scroll to line number from `loc`.
- Expand the dialog to be larger (80% of screen width/height or use `showGeneralDialog` for full-size).
- Add a header with filename, file type icon, location indicator, and "Close" button.

**Acceptance**: Citation links open the correct native viewer per file type. Video seeks to timestamp. PDF opens to page. Image zooms.

---

## Sequencing

```
7.1 (category/pagination) ──┐
                            ├──→ 7.3 (hybrid fusion) ──→ 7.4 (/ask upgrade)
7.2 (embeddings)          ──┘                        ──→ 7.5 (frontend search UI)

7.6 (upload progress) ──→ 7.7 (drag-and-drop)   [independent from search track]
7.8 (source viewer)                               [independent from everything]
```

- **7.1** and **7.2** first, in parallel (independent backend work).
- **7.3** after both 7.1 and 7.2 are done.
- **7.4** and **7.5** after 7.3 (one backend, one frontend — can be parallel).
- **7.6** anytime (independent).
- **7.7** after 7.6 (shares upload state management).
- **7.8** anytime (independent).

---

## New Dependencies

**Backend** (`pyproject.toml` optional group):
```toml
[project.optional-dependencies]
semantic = ["sentence-transformers>=2.2.0"]
```
- Pulls in PyTorch (~2GB). Documented as optional for users who don't need semantic search.
- FTS5 keyword search remains fully functional without it.

**Frontend** (`pubspec.yaml`):
```yaml
desktop_drop: ^0.6.0
media_kit: ^1.1.10
media_kit_video: ^1.1.10
media_kit_libs_windows: ^1.0.9
pdfrx: ^1.0.0
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| `sentence-transformers` + PyTorch is ~2GB | Optional dependency group. FTS5 fallback when not installed. |
| First embedding call is slow (model download + load) | Lazy-load model. Log progress. Cache in memory after load. |
| `media_kit` native deps are complex cross-platform | Target Windows first. macOS/Linux native libs verified in Phase 8. |
| Embedding table grows with wiki size | 384 floats × 4 bytes = 1.5KB/page. 1000 pages = 1.5MB. Negligible. |
| RRF k parameter tuning | Start with k=60 (literature default). Adjust if search quality is poor in testing. |
| FTS5 unavailable on some Python builds | Python's bundled `sqlite3` includes FTS5. Verify with `pragma compile_options` on startup. |
| `desktop_drop` on Linux requires X11/Wayland support | Acceptable: desktop-first app, Linux support refined in Phase 8. |

---

**Note**: Phase 7 completion verification and polish is folded into Phase 8 (task 8.1). Any remaining gaps in upload progress (7.6), drag-and-drop (7.7), or source viewer media support (7.8) are addressed there.
