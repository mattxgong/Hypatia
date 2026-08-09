# Phase 1: Project Scaffolding

**Goal**: Establish the monorepo structure, tooling, database schema, API contract, backend auto-launch mechanism, and dev workflow so all subsequent phases have a stable foundation.

**Prerequisites**: Phase 0.5 (technical spikes validated).

**Outputs**: A runnable (but empty) Flutter app that automatically spawns a FastAPI server, connected database, OpenAPI contract, dev scripts.

---

## Tasks

### 1.1 Initialize monorepo structure
Create the top-level directory layout:
```
hypatia/
├── backend/
├── frontend/
├── data/
├── docs/
├── scripts/
├── README.md
├── .gitignore
└── CLAUDE.md
```
- Write `.gitignore` covering Python (`__pycache__`, `.venv`, `*.pyc`), Flutter (`.dart_tool`, `build/`), and `data/` (runtime user data).
- Initialize git repository.

**Acceptance**: `git status` shows a clean repo with the directory skeleton.

---

### 1.2 Initialize FastAPI backend
- Create `backend/` with `pyproject.toml` and `requirements.txt`.
- Set up a virtual environment.
- Create `app/main.py` with a minimal FastAPI app (`GET /health` returns `{"status": "ok"}`).
- Add `app/__init__.py`, `app/config.py` with Pydantic Settings for configuration (data directory defaulting to `~/.hypatia/data/`, LLM provider defaulting to `anthropic`, API keys, Whisper model size).
- Configure `uvicorn` as the dev server.
- Data directory is `~/.hypatia/data/` by default, configurable via environment variable or settings.
- **Dependency pinning strategy**:
  - Use `pyproject.toml` as the source of truth for direct dependencies (with version constraints like `fastapi>=0.100,<1.0`).
  - Generate a pinned lockfile via `pip-compile` (from `pip-tools`) or `uv lock`: `requirements.lock` with exact versions for reproducible installs.
  - `requirements.txt` remains a thin wrapper that points to the lockfile for production installs.
  - **Version constraint policy**: pin major version (`>=X.0,<X+1`). Allow minor/patch updates within a major.
  - **Update cadence**: Monthly dependency update PR (can be automated with Dependabot or Renovate). Review changelogs for breaking changes before merging.
  - **Flutter/Dart**: `pubspec.lock` already serves as the lockfile — commit it to the repo.
  - Add `pip-tools` or `uv` to dev dependencies.

**Dependencies to install**:
- `fastapi`, `uvicorn[standard]`
- `sqlalchemy`, `aiosqlite` (async SQLite)
- `alembic` (database migrations)
- `pydantic`, `pydantic-settings`
- `python-multipart` (file uploads)
- `anthropic` (default LLM provider)
- `openai`, `httpx` (additional LLM providers)
- `github-copilot-sdk` (Copilot provider — per spike 0.5.2, drives the local Copilot CLI over JSON-RPC rather than hand-rolled REST/OAuth)
- `structlog` (structured logging)
- `tiktoken` (token counting for context budget)
- `keyring` (secure credential storage)

**Acceptance**: `uvicorn app.main:app --reload` starts and `/health` returns 200. A pinned lockfile exists and is committed.

---

### 1.3 Initialize Flutter frontend
- Run `flutter create frontend` with appropriate organization name.
- Set up `pubspec.yaml` with initial dependencies:
  - `flutter_riverpod` (state management)
  - `http` or `dio` (HTTP client)
  - `web_socket_channel` (WebSocket)
  - `flutter_markdown` (markdown rendering)
  - `file_picker` (file selection)
  - `go_router` (routing)
  - `flutter_secure_storage` (secure credential storage)
- Set up `analysis_options.yaml` with strict linting.
- Create the basic `lib/` directory structure (models/, services/, providers/, screens/, widgets/).

**Acceptance**: `flutter run -d <platform>` launches a blank app with no errors.

---

### 1.4 Design and create database schema
Create SQLAlchemy models in `app/models/db_models.py`:

```
classes
├── id (UUID, PK)
├── name (str, unique)
├── description (str, nullable)
├── created_at (datetime)
└── updated_at (datetime)

files
├── id (UUID, PK)
├── class_id (FK -> classes.id)
├── original_filename (str)
├── file_type (str enum: pdf, docx, pptx, xlsx, image, video, audio, markdown, other)
├── file_size_bytes (int)
├── raw_path (str)           # Path to original file in raw/
├── converted_path (str)     # Path to markdown conversion
├── status (str enum: pending, processing, ready, error)
├── error_message (str, nullable)
├── metadata_json (JSON)     # Duration, page count, etc.
├── created_at (datetime)
└── updated_at (datetime)

wiki_pages
├── id (UUID, PK)
├── class_id (FK -> classes.id)
├── path (str)               # Relative path within wiki/
├── title (str)
├── category (str enum: source-summary, concept, entity, synthesis, index, log)
├── content (text)           # Full markdown content
├── source_file_ids (JSON)   # Array of file IDs this page was derived from
├── created_at (datetime)
└── updated_at (datetime)

chat_messages
├── id (UUID, PK)
├── class_id (FK -> classes.id)
├── role (str enum: user, assistant, system)
├── content (text)
├── command (str, nullable)  # /ask, /summarize, /remove, or null
├── metadata_json (JSON)     # Citations, referenced pages, etc.
├── created_at (datetime)
└── updated_at (datetime)
```

Create Pydantic schemas in `app/models/schemas.py` for API request/response types.

**Acceptance**: Database tables can be created and basic CRUD operations work in a test script.

---

### 1.5 Set up database initialization and migrations
- Create `app/database.py` with async SQLAlchemy engine, session factory, and `create_tables()` function.
- Auto-create the `data/` directory and database file on first run.
- **Database migration strategy** — use Alembic from day one:
  - Initialize `alembic/` directory with async SQLAlchemy config.
  - Generate an initial migration from the schema in Task 1.4.
  - On app startup: run `alembic upgrade head` automatically (ensures the DB is always at the latest schema).
  - **Migration workflow**: When a model changes, generate a migration with `alembic revision --autogenerate -m "description"`. Never modify the SQLite file by hand.
  - Migrations are committed to git alongside the code change that requires them.
  - **Downgrade support**: Each migration includes a `downgrade()` for rollback. Test both directions.
  - For user data safety: back up the SQLite file before running migrations that alter or drop columns.

**Acceptance**: Starting the FastAPI app runs pending migrations and creates all tables. Schema changes are always handled via Alembic migrations.

---

### 1.6 Create Pydantic schemas for API contracts
Define request/response models for each entity:
- `ClassCreate`, `ClassRead`, `ClassUpdate`
- `FileRead`, `FileUploadResponse`
- `WikiPageRead`, `WikiPageSummary`
- `ChatMessageCreate`, `ChatMessageRead`
- `CommandRequest`, `CommandResponse`

**Acceptance**: Schemas import cleanly and can serialize/deserialize test data.

---

### 1.7 Set up dev scripts
Create helper scripts in `scripts/`:
- `setup.sh` — creates Python venv, installs dependencies, runs `flutter pub get`
- `run_dev.sh` — starts both backend (`uvicorn`) and frontend (`flutter run`) in parallel
- Document ffmpeg installation requirement

**Acceptance**: A fresh clone can run `scripts/setup.sh && scripts/run_dev.sh` to get a working dev environment.

---

### 1.8 Create CLAUDE.md for the repository
Write a `CLAUDE.md` that describes:
- Repository structure and conventions
- How to run the backend and frontend
- Database location and schema overview
- Coding conventions (Python: black/ruff, Dart: standard lints)
- Testing commands

**Acceptance**: An LLM agent can read CLAUDE.md and understand how to navigate and contribute to the project.

---

### 1.9 Implement backend auto-launch from Flutter
The Flutter app must automatically spawn the FastAPI backend as a child process:
- On app launch: start `uvicorn app.main:app` (or a bundled Python script) as a subprocess.
- Manage the process lifecycle: detect when backend is ready (poll `/health`), restart on crash, kill on app close.
- Create `lib/services/backend_launcher.dart`:
  - `startBackend()` — spawns the Python process, waits for health check.
  - `stopBackend()` — kills the process gracefully (SIGTERM, then SIGKILL after timeout).
  - `isBackendRunning()` — polls the health endpoint.
  - `onBackendReady` — callback/stream that fires when backend is ready to accept requests.
- **Python discovery** (cross-platform):
  - Windows: check `py -3` launcher first, then `python` on PATH, then common install paths (`%LOCALAPPDATA%\Programs\Python\`).
  - macOS/Linux: check `python3` on PATH, then `/usr/local/bin/python3`, then Homebrew paths.
  - Store discovered Python path in local config so subsequent launches are instant.
- **Port management**:
  - Default port 8000. If busy, try 8001-8010.
  - Write the selected port to a temp file so the Flutter frontend knows where to connect.
- **Windows process handling**:
  - Use `Process.start()` with `runInShell: false` to avoid shell intermediary.
  - On Windows, killing a process doesn't kill children. Use `taskkill /T /F /PID` to kill the process tree.
  - Register a shutdown hook via `ProcessSignal.sigterm` (or `AppLifecycleListener` on desktop).
- **First-run setup**:
  - If Python is not found: show a dialog with install instructions and a link.
  - If dependencies aren't installed: run `pip install -r requirements.txt` automatically (show progress).
  - If venv doesn't exist: create it on first run.
- Handle cases: Python not installed, port already in use, backend crashes during startup.
- Display a loading screen in Flutter while the backend is starting up.
- In dev mode: allow connecting to an externally running backend (skip auto-launch).

**Acceptance**: Launching the Flutter app automatically starts the backend on all desktop platforms. Closing the app stops it. Backend crashes are detected and reported. Python discovery works on Windows/macOS/Linux.

---

### 1.10 Define API contract (OpenAPI specification)
Write the initial OpenAPI spec that defines the contract between frontend and backend:
- Create `docs/api-contract.yaml` (or let FastAPI generate it, and snapshot it).
- Define all endpoint paths, request/response shapes, and WebSocket message formats.
- This serves as the shared truth between frontend and backend development:
  - Backend implements against it (FastAPI auto-validates).
  - Frontend `api_client.dart` is written to match it.
- Minimal initial version covering:
  - `GET /health`
  - Classes CRUD
  - Files upload and list
  - Wiki tree and page retrieval
  - Chat WebSocket message schema (`message`, `chunk`, `complete`, `error`, `progress`)
- Include the **progress protocol** for long-running operations:
  - Server sends `{"type": "progress", "operation": "rebuild", "percent": 45, "message": "Processing page 3/7..."}`
  - Client can send `{"type": "cancel", "operation_id": "..."}` to abort.
- Update the spec as new endpoints are added in later phases.

**Acceptance**: OpenAPI spec exists and documents all planned endpoints. Frontend and backend teams can develop against it independently.

---

### 1.11 Set up wiki git versioning infrastructure
Implement the auto-commit mechanism for wiki directories:
- Create `app/services/wiki_git.py`:
  - `init_wiki_repo(class_id)` — runs `git init` in the class's `wiki/` directory.
  - `commit_wiki_change(class_id, message)` — stages all changes and commits with the given message.
  - `get_wiki_history(class_id, page_path=None)` — returns commit log (optionally filtered to a specific page).
  - `revert_wiki_to(class_id, commit_sha)` — resets wiki to a previous state.
- Every wiki-modifying operation auto-commits:
  - Ingest: `"ingest: added source-summary for lecture-1.mp4, created 2 concept pages"`
  - Rebuild: `"rebuild: regenerated 15 pages from 4 sources"`
  - Remove: `"remove: deleted chapter-3-notes and 2 orphaned pages"`
  - User edit: `"user-edit: modified pages/concepts/neural-networks.md"`
- No remote push — purely local git history.
- Handle: git not installed (degrade gracefully, skip versioning with a warning).

**Acceptance**: Wiki changes are auto-committed. Can view history and revert to previous states.

---

### 1.12 Set up CI pipeline
Configure GitHub Actions (or equivalent) for continuous integration:
- **On every push/PR**:
  - Python: `ruff check`, `ruff format --check`, `mypy` type checking.
  - Dart: `flutter analyze`, `dart format --set-exit-if-changed`.
  - Unit tests: `pytest tests/ -m "not integration"` (fast, mock LLM).
  - Flutter tests: `flutter test`.
- **Nightly** (scheduled):
  - Integration tests with real LLM (uses a test API key stored as a secret).
  - Prompt regression tests against golden corpus (Phase 3B.10).
- **Manual trigger**:
  - Cross-platform builds (Windows, macOS, Linux).
  - Full E2E tests (Phase 8).
- Store test API key as a repository secret (never in code).
- Badge in README showing CI status.

**Acceptance**: PRs that break linting, type checks, or unit tests are blocked. Nightly runs catch regressions.

---

### 1.13 Configure structured logging
Set up logging infrastructure from day one in `app/utils/logging.py`:
- Use Python `structlog` for structured JSON logging.
- Every log entry includes: `timestamp`, `level`, `event`, `class_id` (when applicable), `file_id` (when applicable), `operation`, `correlation_id`.
- Log levels:
  - `INFO`: operation start/complete (ingest, rebuild, ask, etc.)
  - `WARNING`: degraded behavior (LLM retry, git not found, etc.)
  - `ERROR`: operation failures (LLM timeout, parse error, disk full)
  - `DEBUG`: LLM prompts sent, raw responses received (opt-in, for debugging prompt issues)
- Log destinations: file (`~/.hypatia/logs/hypatia.log`), rotating (10MB max, keep 5).
- Every LLM call logs: provider, model, token count (input/output), latency, success/failure.
- Correlation IDs link related operations (e.g., file upload → conversion → ingestion → wiki commit).
- Frontend can query recent logs via `GET /api/logs` for a debug panel (Phase 8 polish).

**Acceptance**: All backend operations produce structured logs. Can trace a file from upload through wiki generation by correlation ID.

---

## Sequencing

Execution order in waves. Tasks within a wave have no dependency on each other and can
run in parallel; each wave depends only on tasks from earlier waves.

```
Wave 1: 1.1  (monorepo skeleton)
Wave 2: 1.2  (backend init)          │  1.3  (frontend init)
Wave 3: 1.9  (auto-launch)           │  1.13 (logging)           │  1.11 (wiki git)
Wave 4: 1.4  (db schema)
Wave 5: 1.5  (db init/migrations)    │  1.6  (schemas)
Wave 6: 1.10 (API contract)          │  1.7  (dev scripts)
Wave 7: 1.12 (CI pipeline)
Wave 8: 1.8  (CLAUDE.md)
```

- **Wave 1**: `1.1` unblocks everything else.
- **Wave 2**: `1.2` and `1.3` are fully independent — backend and frontend init don't
  touch each other.
- **Wave 3**: three independent tracks that only need Wave 2 to exist:
  - `1.9` (backend auto-launch) is pulled forward from its naive "needs everything"
    position. Spike 0.5.3 already validated the full approach end-to-end in
    `spikes/flutter_subprocess/` (Python discovery, port handling, health polling,
    `taskkill /T /F`, graceful shutdown) — this task is now mostly porting that
    validated code into `lib/services/backend_launcher.dart` against the `/health`
    endpoint from 1.2, not building it from scratch. Lower risk, no reason to defer it.
  - `1.13` (logging) should be wired immediately after 1.2 so the db/schema work in
    Wave 4+ can use it from the start rather than being retrofitted.
  - `1.11` (wiki git) only needs backend structure and is small/isolated.
- **Wave 4**: `1.4` (db schema) is a single dependency root for the rest of the DB layer.
- **Wave 5**: `1.5` (migrations) and `1.6` (Pydantic schemas) both depend only on `1.4`.
- **Wave 6**: `1.10` (API contract) depends on `1.6` (schemas define the contract
  shapes); `1.7` (dev scripts) depends on `1.2` + `1.3` (both already exist by now).
- **Wave 7**: `1.12` (CI) should come after there's real lint config and a few tests to
  run — wiring CI against an empty project has nothing to check.
- **Wave 8**: `1.8` (CLAUDE.md) is last, since it documents the finished result.

**Dependency note**: `1.2`'s dependency list now includes `github-copilot-sdk`
(alongside `anthropic`/`openai`/`httpx`) per spike 0.5.2's finding that the Copilot
provider should drive the official SDK/CLI rather than hand-rolled REST + OAuth —
adding it during `1.2` avoids a later dependency-add pass when `copilot_provider.py`
is implemented in Phase 3.
