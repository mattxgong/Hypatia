# CLAUDE.md

Guidance for an LLM agent (or human) contributing to Hypatia.

## What Hypatia is

Hypatia is a cross-platform Flutter application with a FastAPI Python backend
that lets users create **Classes** — independent, self-contained study wikis.
Each Class has its own repository of uploaded source material (lecture videos,
notes, PDFs, slides, images, etc.) and an LLM-maintained wiki built from that
material. Users interact with their Class through a chat interface that
supports querying, summarizing, and managing the knowledge base.

The core idea is the **LLM Wiki pattern**: instead of re-deriving answers from
raw documents on every query (like RAG), the LLM incrementally builds and
maintains a persistent, interlinked wiki of markdown pages. See
`docs/plan/00-master-plan.md` for the full architecture overview and phase
breakdown, and `docs/plan/` for the per-phase task plans.

## Repository structure

```
backend/            FastAPI Python backend
  app/
    main.py          FastAPI app, lifespan (DB init/migrations), HTTP logging middleware
    config.py        Pydantic Settings (HYPATIA_-prefixed env vars, .env support)
    database.py      Async SQLAlchemy engine/session, Alembic migration runner
    models/
      db_models.py    SQLAlchemy ORM models (the DB schema)
      schemas.py      Pydantic API schemas (request/response bodies)
    services/
      wiki_git.py     Per-Class git repo for wiki version history (init/commit/history/revert)
      file_converter.py  MarkItDown-based document-to-markdown conversion
      video_processor.py ffmpeg + faster-whisper transcription pipeline
      storage_service.py Per-Class file storage with path-traversal-safe filenames
      summary_generator.py Heuristic source summaries (no LLM)
      llm_service.py     LLM provider abstraction + factory (Phase 3)
      llm_providers/     Concrete LLM implementations (Phase 3):
        copilot_provider.py   Default: github-copilot-sdk (Copilot CLI + BYOK Ollama)
        anthropic_provider.py Direct Anthropic SDK
        openai_provider.py    Direct OpenAI SDK (also Ollama via base_url)
    utils/
      logging.py      structlog JSON logging setup (rotating file handler + stdout)
  alembic/            Alembic migration environment + versions/
  tests/              pytest test suite
  pyproject.toml      Deps, ruff, mypy, pytest config

frontend/            Flutter application
  lib/
    main.dart          App entry point
    services/
      backend_launcher.dart   Launches/manages the backend subprocess
    models/ providers/ screens/ widgets/   Scaffolded, empty until later phases

data/                Runtime data (gitignored; DB, wiki repos, uploaded files live here)
docs/
  plan/               Phase-by-phase implementation plans (00-master-plan.md is the index)
  api-contract.yaml   OpenAPI contract between frontend and backend
scripts/
  setup.sh            One-time dev environment setup (backend venv + deps, flutter pub get)
  run_dev.sh          Runs backend (uvicorn --reload) and frontend (flutter run) together
spikes/               Early technical spikes/prototypes (Phase 0.5), not part of the app
.github/workflows/    CI (ci.yml), nightly (nightly.yml), manual (manual.yml)
```

## Running the project

First-time setup:

```bash
scripts/setup.sh
```

This creates `backend/.venv`, installs backend deps (`pip install -e ".[dev]"`),
and runs `flutter pub get` in `frontend/`. It also reminds you to install
`ffmpeg`, which the backend needs for audio/video conversion.

Run both backend and frontend for local development:

```bash
scripts/run_dev.sh
```

This starts `uvicorn app.main:app --reload --port 8000` in `backend/` and
`flutter run` in `frontend/`, and stops the backend when `flutter run` exits.
In production/normal use, the Flutter app auto-launches the backend itself
(see `frontend/lib/services/backend_launcher.dart` and Task 1.9); `run_dev.sh`
is only for iterating on both sides at once with backend auto-reload.

To run just the backend:

```bash
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000   # Windows
.venv/bin/python -m uvicorn app.main:app --reload --port 8000           # macOS/Linux
```

## Database

- SQLite, single file at `<data_dir>/hypatia.db`, where `data_dir` defaults to
  `~/.hypatia/data` (overridable via the `HYPATIA_DATA_DIR` env var / `.env`;
  see `backend/app/config.py`).
- Schema is defined with SQLAlchemy 2.0 async ORM models in
  `backend/app/models/db_models.py` and versioned with Alembic
  (`backend/alembic/`). Migrations run automatically on backend startup via
  the FastAPI `lifespan` in `app/main.py`.
- Four tables:
  - `classes` — a Class (name, description, timestamps).
  - `files` — uploaded source material for a Class (`file_type`, `status`,
    `raw_path`/`converted_path`, `metadata_json`).
  - `wiki_pages` — LLM-maintained wiki pages for a Class (`path`, `title`,
    `category`, `content`, `source_file_ids`).
  - `chat_messages` — chat history for a Class (`role`, `content`, `command`,
    `metadata_json`).
- Enums (`FileType`, `FileStatus`, `WikiCategory`, `ChatRole`) are Python
  `str` enums stored by their string `.value` (via a `values_callable` helper),
  not by member name — e.g. `WikiCategory.SOURCE_SUMMARY` is stored as
  `"source-summary"`.
- After changing `db_models.py`, generate a new migration:
  ```bash
  cd backend
  alembic revision --autogenerate -m "description of the change"
  ```

## API contract

`docs/api-contract.yaml` is the OpenAPI contract between the frontend and
backend (health check, Classes CRUD, file upload/list, wiki tree/page
retrieval, and the chat WebSocket message protocol). Keep it in sync with
`backend/app/models/schemas.py` and the actual routes as endpoints are added.

## Logging

The backend uses `structlog` for structured JSON logging
(`backend/app/utils/logging.py`): a rotating file handler writes to
`<logs_dir>/hypatia.log` (`logs_dir` defaults to `~/.hypatia/logs`, also
configurable via `HYPATIA_LOGS_DIR`), mirrored to stdout. Per-request context
(`correlation_id`, `class_id`, `file_id`, `operation`) is bound via contextvars
and attached to every log line for the duration of a request/operation.

## Coding conventions

**Python (backend)**:
- Formatted and linted with [ruff](https://docs.astral.sh/ruff/) —
  `line-length = 100`, `target-version = "py311"` (see `backend/pyproject.toml`).
  There is no separate black step; `ruff format` is the formatter.
- Type-checked with `mypy` (`python_version = "3.11"`, `ignore_missing_imports = true`).
- SQLAlchemy 2.0 style: `DeclarativeBase`, `Mapped[...]` / `mapped_column`.
- Settings live in `app/config.py` as a single Pydantic `Settings` singleton
  (`settings`), populated from `HYPATIA_*` env vars / a `.env` file.

**Dart (frontend)**:
- Formatted with `dart format` and linted with `flutter analyze`, using the
  standard Flutter/Dart lint set (see `frontend/analysis_options.yaml`).

## Testing and quality checks

These are exactly the checks CI runs (`.github/workflows/ci.yml`); run them
locally before committing:

```bash
# Backend (from backend/, with .venv active or using .venv's python directly)
ruff check .
ruff format --check .
mypy app
pytest tests/ -m "not integration"     # fast unit tests, mocked LLM

# Frontend (from frontend/)
flutter analyze
dart format --set-exit-if-changed .
flutter test
```

Integration tests that need a real LLM API key are marked `@pytest.mark.integration`
and excluded from the fast run above; they run nightly instead
(`.github/workflows/nightly.yml`) via `pytest tests/ -m integration`.

`.github/workflows/manual.yml` is a manually-triggered (`workflow_dispatch`)
workflow that builds cross-platform Flutter desktop binaries and will run the
full end-to-end suite once it exists (Phase 8).

## Conventions for contributions

- Don't add abstractions, error handling, or config for scenarios the current
  phase doesn't need — follow the phase-by-phase plans in `docs/plan/`.
- Keep `docs/api-contract.yaml` and `backend/app/models/schemas.py` consistent
  with each other and with the actual implemented routes.
- Never commit secrets; API keys are read from env vars / `.env`
  (`.env` is gitignored) or, for nightly CI, from repository secrets.
