# Phase 4: Backend API

**Goal**: Expose all backend services (Classes, Files, Wiki, Chat) through a clean REST + WebSocket API that the Flutter frontend can consume. Includes a progress protocol for long-running operations.

**Prerequisites**: Phase 3A (wiki engine spike — ingest + /ask working). Phase 3B completed in parallel.

**Outputs**: A complete API layer that the frontend can integrate against. API documentation auto-generated via FastAPI's OpenAPI.

**What already exists** (from earlier phases):
- `app/routers/files.py` — upload, list, get-by-id with background processing (Phase 2, Task 2.9)
- `app/main.py` — correlation-ID + request-timing logging middleware (Phase 1)
- `app/services/wiki_engine.py` — all command handlers: `ingest_source`, `handle_ask`, `handle_ask_stream`, `handle_summarize`, `handle_remove`, `handle_lint`, `handle_rebuild_preview`, `handle_rebuild`, `handle_export` (Phases 3A + 3B)
- `app/services/task_manager.py` — in-memory task registry with start/update/cancel/complete/fail/get/list (Phase 3B)
- `app/services/ingestion_queue.py` — per-Class sequential queue with asyncio background tasks (Phase 3A)
- `app/services/llm_providers/base.py` — `LLMProvider.stream()` returns `AsyncIterator[str]` (Phase 3A)
- `docs/api-contract.yaml` — WebSocket protocol schemas (ChatWsMessage/Chunk/Complete/Error/Progress/Cancel) designed in Phase 1

---

## Tasks

### 4.1 Add CORS and error-handling middleware
In `app/main.py` and `app/config.py`:
- Add `CORSMiddleware` allowing `localhost:*` origins (Flutter dev) + configurable `HYPATIA_CORS_ORIGINS` list setting.
- Add exception handlers: `HTTPException` → `{"detail": "...", "code": "ERROR_CODE"}` JSON; unhandled exceptions → 500 with generic message (log full traceback).
- Define `LLMUnavailableError` (custom exception mapping to 503, `code: "LLM_UNAVAILABLE"`).
- The existing correlation-ID middleware stays as-is.

**Acceptance**: Flutter app can call the backend without CORS errors. All error responses are structured JSON with `detail` + `code`.

---

### 4.2 Implement Classes router
Create `app/routers/classes.py`:
- `POST /api/classes` — create a new Class (name, description). Creates the data directory tree (`raw/`, `converted/`, `wiki/`, `thumbnails/`) via `storage_service`. Initializes wiki git repo via `wiki_git.init_wiki_repo()`.
- `GET /api/classes` — list all Classes.
- `GET /api/classes/{class_id}` — get a single Class with stats (file count, page count from DB counts).
- `PUT /api/classes/{class_id}` — update Class name/description.
- `DELETE /api/classes/{class_id}` — delete a Class, remove its entire data directory, cascade-delete DB records (files, wiki_pages, chat_messages).

Register router in `app/main.py`.

**Acceptance**: Full CRUD on Classes via API. Creating a Class creates the directory tree and git-initialized wiki.

---

### 4.3 Extend Files router
Add missing endpoints to the existing `app/routers/files.py`:
- `GET /api/classes/{class_id}/files/{file_id}/raw` — serve the original raw file via `FileResponse`.
- `GET /api/classes/{class_id}/files/{file_id}/converted` — serve the converted markdown via `FileResponse`.
- `DELETE /api/classes/{class_id}/files/{file_id}` — call `wiki_engine.handle_remove()` for wiki cleanup, delete raw/converted files from disk, remove DB record.
- `GET /api/classes/{class_id}/files/{file_id}/open?loc=...` — serve raw file with `X-Location` response header containing the location hint (for deep-link citations: `page:5`, `t:342`, `line:42`).

**Acceptance**: Can download raw/converted files, delete files with wiki cleanup, and resolve citation deep-links.

---

### 4.4 Implement Wiki router
Create `app/routers/wiki.py`:
- `GET /api/classes/{class_id}/wiki/tree` — query `wiki_pages` table, return `list[WikiPageSummary]` (frontend groups by path into a tree).
- `GET /api/classes/{class_id}/wiki/pages/{page_path:path}` — return full `WikiPageRead` for a specific page.
- `GET /api/classes/{class_id}/wiki/index` — return the index page content (shorthand for the `index` category page).
- `PUT /api/classes/{class_id}/wiki/pages/{page_path:path}` — user edit: update DB content, write to disk, commit via `wiki_git.commit_wiki_change()`.
- `GET /api/classes/{class_id}/wiki/search?q=...` — delegate to `wiki_search.search_wiki_pages()`.
- `POST /api/classes/{class_id}/wiki/export` — call `handle_export()`, return the ZIP as a streaming `FileResponse`.
- `POST /api/classes/{class_id}/wiki/lint` — call `handle_lint()`, return lint report as JSON.
- `POST /api/classes/{class_id}/wiki/rebuild` — default returns preview via `handle_rebuild_preview()`; with `?confirm=true`, dispatches `handle_rebuild()` as a background task (tracked via `task_manager`).

Register router in `app/main.py`.

**Acceptance**: Can browse the wiki tree, read any page, edit pages, trigger search/export/lint/rebuild. Rebuild uses task_manager for progress.

---

### 4.5 Implement command parser
Create `app/utils/command_parser.py`:
- Parse chat input for known commands: `/ask`, `/summarize`, `/remove`, `/lint`, `/rebuild`, `/export`.
- Return `ParsedCommand(command="ask", args="the query text")`.
- Bare messages (no `/` prefix) default to `command="ask"` with the full text as args.
- Unknown `/foo` commands raise `ValueError` with a message listing valid commands.

**Acceptance**: All six commands parse correctly. Bare messages default to /ask. Invalid commands produce helpful errors.

---

### 4.6 Implement Chat router with WebSocket
Create `app/routers/chat.py`:
- `WebSocket /api/classes/{class_id}/chat` — real-time chat connection implementing the protocol from `docs/api-contract.yaml`:
  - Receive `ChatWsMessage` → parse with command_parser → route to handler.
  - `/ask`: iterate `handle_ask_stream()`, send `ChatWsChunk` per yielded token, then `ChatWsComplete` with message_id + citations.
  - `/summarize`, `/lint`, `/export`, `/remove`: run handler synchronously, send result as `ChatWsComplete`.
  - `/rebuild`: start as background task via `task_manager`; spawn asyncio polling loop (every 500ms) that pushes `ChatWsProgress` frames; support `ChatWsCancel` to call `task_manager.cancel_task()`.
  - On error: send `ChatWsError` with message + code.
  - Persist user messages and assistant responses to `chat_messages` table.
- `GET /api/classes/{class_id}/chat/history?limit=50&offset=0` — paginated chat history (newest first).
- `DELETE /api/classes/{class_id}/chat/history` — clear chat history for a Class.

Register router in `app/main.py`.

**Acceptance**: WebSocket connects, commands are parsed and routed, LLM responses stream back in real-time, progress frames push for rebuild, cancel stops the operation.

---

### 4.7 Implement task status REST endpoints
Create `app/routers/tasks.py`:
- `GET /api/classes/{class_id}/tasks` — list active/recent tasks (delegates to `task_manager.list_tasks(class_id)`).
- `GET /api/classes/{class_id}/tasks/{task_id}` — get single task status.
- `POST /api/classes/{class_id}/tasks/{task_id}/cancel` — cancel a running task.

Register router in `app/main.py`.

**Acceptance**: Task status is queryable via REST. Cancel request stops the operation.

---

### 4.8 Implement Class backup and import
Add to `app/routers/classes.py` (or separate `app/routers/backup.py` if needed):
- `POST /api/classes/{class_id}/backup` — export entire Class as a portable ZIP archive:
  - Includes: raw files, converted files, wiki directory (with git history), thumbnails, DB records serialized as JSON manifest.
  - Strips absolute paths (all relative to class root).
  - Returns ZIP as streaming download.
- `POST /api/classes/import` — import a Class from a backup archive:
  - Extracts to a new class directory, assigns new class_id.
  - Rebuilds DB records from the JSON manifest.
  - Validates integrity (file counts, wiki index consistency).

**Acceptance**: Can backup a Class on one machine and restore it on another with all data intact.

---

### 4.9 Add graceful degradation
- Create a `check_llm_available()` FastAPI dependency:
  - Attempts a minimal LLM call (`provider.complete("test", "ping", max_tokens=1)`) with a short timeout.
  - Caches result for 30 seconds to avoid repeated probes.
  - On failure, raises `LLMUnavailableError` (→ 503).
- Apply to LLM-dependent chat commands (`/ask`, `/summarize`, `/lint`, `/rebuild`) and wiki rebuild.
- LLM-independent endpoints (GET classes/files/wiki, search, `/export`, `/remove`, health) never check LLM availability.
- Frontend uses this classification to show/disable features appropriately.

**Acceptance**: LLM-independent endpoints work even when the LLM provider is down. LLM-dependent endpoints return 503 with `LLM_UNAVAILABLE` code when the provider is unreachable.

---

### 4.10 Update API contract
Update `docs/api-contract.yaml` to reflect all implemented endpoints:
- Add Classes CRUD, file serving/delete/deep-link, wiki CRUD/commands, chat history, task status, backup/import.
- Add new schemas: `ClassReadWithStats`, `TaskStatus`, `LintReport`, `RebuildPreview`, `BackupManifest`.
- Keep existing WebSocket protocol schemas (already correct).

**Acceptance**: `api-contract.yaml` matches the actual implemented routes and response shapes.

---

### 4.11 Write API integration tests
Test each endpoint with `httpx.AsyncClient` (FastAPI test client) and WebSocket test session:
- Classes CRUD (create with directory setup, list, get with stats, update, delete with cascade).
- Files: raw/converted serving, delete with wiki cleanup, deep-link location header.
- Wiki: tree, page read, user edit + git commit, search, export, lint, rebuild (preview + confirmed).
- Chat WebSocket: connect, message → chunks → complete flow, command parsing, error frames, progress + cancel for rebuild.
- Tasks REST: list, get, cancel.
- CORS headers present in responses.
- Error format consistency (all errors have `detail` + `code`).
- Graceful degradation: mock LLM unavailable → 503 on dependent endpoints, 200 on independent ones.

**Acceptance**: All API endpoints are tested. WebSocket flow is tested. Graceful degradation is tested.

---

## Sequencing

```
4.1 (CORS + error middleware) ─── do first, all routes depend on it
  │
  ├── 4.2 (classes router) ─── foundation, other routers need class_id
  │     │
  │     ├── 4.3 (extend files router)
  │     ├── 4.4 (wiki router)
  │     ├── 4.5 (command parser) ──┐
  │     │                          ├── 4.6 (chat WebSocket)
  │     ├── 4.7 (task status REST)─┘
  │     └── 4.8 (class backup/import)
  │
  ├── 4.9 (graceful degradation) ─── applied after LLM-dependent routes exist
  └── 4.10 (update API contract) ─── after all endpoints implemented
       └── 4.11 (integration tests) ─── last
```

- 4.1 first (middleware foundation).
- 4.2 next (classes are the root resource; all other routers are scoped to a class).
- 4.3, 4.4, 4.5, 4.7, 4.8 can proceed in parallel after 4.2.
- 4.6 depends on 4.5 (command parser).
- 4.9 applied after the LLM-dependent routes exist.
- 4.10 and 4.11 are finalization tasks.
