# Phase 4: Backend API

**Goal**: Expose all backend services (Classes, Files, Wiki, Chat) through a clean REST + WebSocket API that the Flutter frontend can consume. Includes a progress protocol for long-running operations.

**Prerequisites**: Phase 3A (wiki engine spike — ingest + /ask working). Phase 3B can continue in parallel.

**Outputs**: A complete API layer that the frontend can integrate against. API documentation auto-generated via FastAPI's OpenAPI.

---

## Tasks

### 4.1 Implement Classes router
Create `app/routers/classes.py`:
- `POST /api/classes` — create a new Class (name, description). Creates the data directory structure.
- `GET /api/classes` — list all Classes.
- `GET /api/classes/{class_id}` — get a single Class with stats (file count, page count).
- `PUT /api/classes/{class_id}` — update Class name/description.
- `DELETE /api/classes/{class_id}` — delete a Class and all its data (with confirmation).

**Acceptance**: Full CRUD on Classes via API. Creating a Class creates the directory tree.

---

### 4.2 Implement Files router
Create `app/routers/files.py`:
- `POST /api/classes/{class_id}/files` — upload one or more files. Saves to `raw/`, creates DB record with `status: "pending"`, kicks off background processing.
- `GET /api/classes/{class_id}/files` — list all files in a Class with status.
- `GET /api/classes/{class_id}/files/{file_id}` — get file details (metadata, status, paths).
- `GET /api/classes/{class_id}/files/{file_id}/raw` — serve the original raw file for download/viewing.
- `GET /api/classes/{class_id}/files/{file_id}/converted` — serve the markdown conversion.
- `DELETE /api/classes/{class_id}/files/{file_id}` — triggers the /remove workflow (file + wiki cleanup).
- Handle multipart file upload with size limits.
- Return processing status so the frontend can show progress.

**Acceptance**: Can upload files, track processing status, download raw/converted versions, delete with cleanup.

---

### 4.3 Implement Wiki router
Create `app/routers/wiki.py`:
- `GET /api/classes/{class_id}/wiki/tree` — returns the wiki page tree structure for the sidebar.
- `GET /api/classes/{class_id}/wiki/pages/{page_path}` — returns the content of a specific wiki page.
- `GET /api/classes/{class_id}/wiki/index` — returns the wiki index page.
- `POST /api/classes/{class_id}/wiki/rebuild` — triggers a full wiki rebuild (re-ingest all sources).
- `GET /api/classes/{class_id}/wiki/search?q=...` — search wiki pages (basic text match initially, upgraded in Phase 7).
- `PUT /api/classes/{class_id}/wiki/pages/{page_path}` — update a wiki page (user edit). Marks the page as user-edited.
- `POST /api/classes/{class_id}/wiki/export` — triggers wiki export, returns download URL.
- `POST /api/classes/{class_id}/wiki/lint` — triggers wiki health check, returns lint report.

**Acceptance**: Can browse the wiki tree, read any page, edit pages, trigger a rebuild, export, and lint. Pages contain rendered markdown with citations.

---

### 4.4 Implement Chat router with WebSocket
Create `app/routers/chat.py`:
- `WebSocket /api/classes/{class_id}/chat` — real-time chat connection:
  - Client sends: `{"type": "message", "content": "/ask what is backpropagation?"}`
  - Server streams back: `{"type": "chunk", "content": "Backpropagation is..."}` (token-by-token)
  - Server sends final: `{"type": "complete", "message_id": "...", "citations": [...]}`
- `GET /api/classes/{class_id}/chat/history` — returns past chat messages (paginated).
- `DELETE /api/classes/{class_id}/chat/history` — clears chat history for a Class.
- Parse incoming messages for commands: `/ask`, `/summarize`, `/remove`.
- Route commands to the appropriate wiki engine handler.
- Non-command messages are treated as `/ask` by default.

**Acceptance**: WebSocket connects, commands are parsed and routed, LLM responses stream back in real-time.

---

### 4.5 Implement command parsing
Create a command parser (can live in `app/routers/chat.py` or `app/utils/`):
- Parse chat input for known commands:
  - `/ask "<query>"` or `/ask <query>` — route to `wiki_engine.handle_ask()`
  - `/summarize <topic>` — route to `wiki_engine.handle_summarize()`
  - `/remove <file-path>` — route to `wiki_engine.handle_remove()`
  - `/lint` — route to `wiki_engine.handle_lint()`
  - `/rebuild` — route to `wiki_engine.handle_rebuild()` (with confirmation)
  - `/export` — route to `wiki_engine.handle_export()`
  - No command prefix — treat as `/ask` with the full message as query
- Return structured parse result: `{command: str, args: str}` or `{command: "ask", args: "raw input"}`.
- Handle invalid commands with a helpful error message.

**Acceptance**: All six commands parse correctly. Bare messages default to /ask. Invalid commands return errors.

---

### 4.6 Configure CORS and middleware
In `app/main.py`:
- Add CORS middleware to allow the Flutter app to connect (localhost during dev, configurable origins).
- Add request logging middleware.
- Add error handling middleware (convert exceptions to proper HTTP error responses).
- Configure max upload size (3GB).

**Acceptance**: Flutter app can make API calls without CORS errors. Errors are returned as structured JSON. Upload limit is enforced.

---

### 4.7 Implement file serving with deep-link support
Extend `app/routers/files.py`:
- `GET /api/classes/{class_id}/files/{file_id}/open?loc=...` — serves the raw file with location hint.
  - For PDFs: `?loc=page:5` — the frontend uses this to open the PDF at page 5.
  - For videos: `?loc=t:342` — the frontend uses this to seek the video to timestamp 342.
  - For text/markdown: `?loc=line:42` — the frontend uses this to scroll to line 42.
- This endpoint resolves the `hypatia://cite` URIs from wiki pages into actual file access.

**Acceptance**: Citation links in wiki pages can be resolved to file access with location information.

---

### 4.8 Add API error handling and validation
- Validate all inputs with Pydantic (request body, path params, query params).
- Return consistent error format: `{"detail": "message", "code": "ERROR_CODE"}`.
- Handle: Class not found, File not found, Wiki page not found, Processing in progress, LLM error, File too large, Unsupported format.
- Add rate limiting for LLM-powered endpoints (prevent rapid-fire expensive calls).
- **Graceful degradation** — classify endpoints by LLM dependency:
  - **LLM-independent** (always work): GET classes/files/wiki, search, /export, /remove, settings, health. These must never fail due to LLM issues.
  - **LLM-dependent** (may fail gracefully): /ask, /summarize, /lint, /rebuild, ingest. When LLM is unavailable, return `503 Service Unavailable` with `{"detail": "LLM provider unavailable", "code": "LLM_UNAVAILABLE", "suggestion": "Check your API key or try again later"}`.
- Frontend uses this classification to show/disable features appropriately.

**Acceptance**: All error cases return appropriate HTTP status codes and structured error messages. LLM-independent endpoints work even when the LLM provider is down.

---

### 4.9 Implement class backup (full import/export)
Add endpoints for full Class portability:
- `POST /api/classes/{class_id}/backup` — export the entire Class as a portable archive:
  - Includes: raw files, converted files, wiki directory (with git history), thumbnails, database records (serialized as JSON).
  - Returns a ZIP or tar.gz file.
  - Strips absolute paths — all paths are relative to the class root.
- `POST /api/classes/import` — import a Class from a backup archive:
  - Extracts archive to a new class directory.
  - Rebuilds database records from the serialized JSON.
  - Assigns a new class_id (avoids collisions).
  - Validates integrity (file counts match, wiki index is consistent).
- This is distinct from `/export` (which only exports wiki markdown). This is a full machine-to-machine transfer.
- Use case: move a Class to a new computer, share with a colleague, backup before risky operations.

**Acceptance**: Can backup a Class on one machine and restore it on another with all data intact.

---

### 4.10 Implement long-running operation progress endpoints
Create infrastructure for progress reporting and cancellation of expensive operations:
- **WebSocket progress events**: Extend the chat WebSocket (or create a separate `/api/classes/{class_id}/events` WebSocket) to push progress updates:
  ```json
  {"type": "progress", "task_id": "abc123", "operation": "rebuild", "percent": 45, "message": "Processing page 3/7..."}
  {"type": "progress", "task_id": "abc123", "operation": "rebuild", "percent": 100, "message": "Complete"}
  {"type": "error", "task_id": "abc123", "operation": "rebuild", "message": "LLM provider error: rate limited"}
  ```
- `POST /api/classes/{class_id}/tasks/{task_id}/cancel` — request cancellation of a running operation.
- `GET /api/classes/{class_id}/tasks` — list active/recent tasks with their status.
- `GET /api/classes/{class_id}/tasks/{task_id}` — get status of a specific task.
- Operations that support progress: `/rebuild`, `/lint`, large file ingestion, `/export`.
- Frontend shows: progress bar, operation description, cancel button.
- On cancellation: operation rolls back to previous git commit (clean state).

**Acceptance**: Long-running operations push progress to the client. Cancel request stops the operation and rolls back. Task status is queryable.

---

### 4.11 Write API integration tests
- Test each endpoint with `httpx.AsyncClient` (FastAPI test client).
- Test file upload + processing flow end-to-end.
- Test WebSocket chat connection and message flow.
- Test command parsing and routing.
- Test error cases (missing class, bad file, invalid command).
- Test CORS headers.

**Acceptance**: All API endpoints are tested. WebSocket flow is tested.

---

## Sequencing

```
4.6 (CORS/middleware) — do first, needed by everything
4.1 (classes) ──→ 4.2 (files) ──→ 4.7 (deep links)
             ──→ 4.3 (wiki)
             ──→ 4.4 (chat) ←── 4.5 (command parsing)
             ──→ 4.9 (class backup) ← depends on 4.1 + 4.2
4.8 (error handling + degradation) — applied throughout, finalized last
4.10 (progress endpoints) — after 4.4 (extends WebSocket)
4.11 (tests) — after all above
```

- 4.6 first (middleware).
- 4.1 (classes) is the foundation (other routers are scoped to a class).
- 4.2, 4.3, 4.4 can be built in parallel after 4.1.
- 4.5 feeds into 4.4.
- 4.7 extends 4.2.
- 4.8 is applied throughout but finalized last (includes graceful degradation classification).
- 4.9 (class backup) depends on classes + files existing.
- 4.10 extends the WebSocket for progress reporting.
- 4.11 is last.
