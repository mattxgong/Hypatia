# Hypatia - Master Implementation Plan

## Vision

Hypatia is a cross-platform Flutter application with a FastAPI Python backend that lets users create **Classes** — independent, self-contained study wikis. Each Class has its own repository of uploaded source material (lecture videos, notes, PDFs, slides, images, etc.) and an LLM-maintained wiki built from that material. Users interact with their Class through a chat interface that supports querying, summarizing, and managing their knowledge base.

The core innovation is the **LLM Wiki pattern**: instead of re-deriving answers from raw documents on every query (like RAG), the LLM incrementally builds and maintains a persistent, interlinked wiki of markdown pages. Knowledge compounds over time — cross-references are pre-built, contradictions are flagged, and synthesis reflects everything ingested so far.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Flutter Frontend                      │
│  ┌─────────┐   ┌───────────────┐   ┌────────────────┐  │
│  │ Sidebar  │   │  Wiki Viewer  │   │  Chat Panel    │  │
│  │ - Class  │   │  - Markdown   │   │  - /ask        │  │
│  │   select │   │  - Citations  │   │  - /summarize  │  │
│  │ - Wiki   │   │  - Deep links │   │  - /remove     │  │
│  │   tree   │   │               │   │  - File upload │  │
│  │ - Search │   │               │   │                │  │
│  └─────────┘   └───────────────┘   └────────────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP / WebSocket
┌──────────────────────┴──────────────────────────────────┐
│                   FastAPI Backend                         │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │  Routers   │  │   Services   │  │   Storage       │  │
│  │ - classes  │  │ - wiki_engine│  │ - raw/          │  │
│  │ - files    │  │ - converter  │  │ - wiki/         │  │
│  │ - wiki     │  │ - video_proc │  │ - converted/    │  │
│  │ - chat     │  │ - llm        │  │ - thumbnails/   │  │
│  └────────────┘  │ - search     │  └─────────────────┘  │
│                  └──────────────┘                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │              SQLite Database                      │   │
│  │  classes | files | wiki_pages | chat_history      │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## Phase Summary

| Phase | Name | Description | Est. Tasks |
|-------|------|-------------|------------|
| 0.5 | [Technical Spike](./005-technical-spike.md) | Validate faster-whisper, LLM parsing, Flutter subprocess | 3 |
| 1 | [Project Scaffolding](./01-scaffolding.md) | Monorepo setup, tooling, CI, database schema, API contract, backend auto-launch | 13 |
| 2 | [File Processing Pipeline](./02-file-processing.md) | MarkItDown integration, faster-whisper video processing, storage | 10 |
| 3A | [Wiki Engine — Spike](./03-wiki-engine.md#phase-3a-wiki-engine-spike) | Single-source ingestion + /ask working end-to-end | 8 |
| 3B | [Wiki Engine — Full](./03-wiki-engine.md#phase-3b-wiki-engine-full) | All 6 commands, user edits, git versioning, prompt testing | 13 |
| 4 | [Backend API](./04-backend-api.md) | REST endpoints, WebSocket chat, file upload, progress protocol | 12 |
| 5 | [Frontend Shell](./05-frontend-shell.md) | Flutter app shell, 3-panel layout, navigation | 8 |
| 6 | [Frontend Features](./06-frontend-features.md) | Wiki viewer, chat panel, file management, user edits | 14 |
| 7 | [Search & Retrieval](./07-search.md) | Full-text search, hybrid retrieval, search UI | 6 |
| 8 | [Integration & Polish](./08-integration.md) | E2E testing, error handling, cross-platform, backend bundling | 8 |

**Total estimated tasks: ~97**

---

## Dependency Graph

```
Phase 0.5 (Technical Spike)
  │
  └──→ Phase 1 (Scaffolding)
         │
         ├──→ Phase 2 (File Processing)
         │       │
         │       └──→ Phase 3A (Wiki Engine Spike) ──→ Phase 3B (Wiki Engine Full)
         │                                                    │
         ├──→ Phase 4 (Backend API) ←────────────────────────┘
         │       │                                       ──→ Phase 7 (Search)
         └──→ Phase 5 (Frontend Shell)
                 │
                 └──→ Phase 6 (Frontend Features) ──→ Phase 8 (Integration)
```

- **Phase 0.5** validates high-risk integrations before committing to the full plan.
- **Phase 1** is the foundation; everything depends on it.
- **Phase 2** (file processing) and **Phase 5** (frontend shell) can run in parallel after Phase 1.
- **Phase 3A** (wiki spike) gets a single source ingestion + /ask working end-to-end. This unblocks frontend integration early.
- **Phase 3B** (wiki full) adds remaining commands, user edits, git versioning, and prompt testing.
- **Phase 4** (backend API) can begin after 3A (enough services to expose).
- **Phase 6** (frontend features) depends on both Phase 4 (API to call) and Phase 5 (shell to render in).
- **Phase 7** (search) can begin once the wiki engine produces pages (after 3A).
- **Phase 8** (integration) is the final phase, depends on everything.

---

## Proposed File Structure

```
hypatia/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app entry point
│   │   ├── config.py                  # Settings (LLM keys, paths, DB)
│   │   ├── database.py                # SQLite connection & session
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── db_models.py           # SQLAlchemy ORM models
│   │   │   └── schemas.py             # Pydantic request/response schemas
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── classes.py             # CRUD for Classes
│   │   │   ├── files.py               # File upload, list, delete
│   │   │   ├── wiki.py                # Wiki page read, rebuild
│   │   │   └── chat.py                # Chat (WebSocket + REST)
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── wiki_engine.py         # Core LLM wiki pattern logic
│   │   │   ├── file_converter.py      # MarkItDown wrapper
│   │   │   ├── video_processor.py     # ffmpeg + faster-whisper
│   │   │   ├── llm_service.py         # LLM provider abstraction
│   │   │   ├── llm_providers/         # Concrete provider implementations
│   │   │   │   ├── __init__.py
│   │   │   │   ├── anthropic_provider.py   # Claude (default)
│   │   │   │   ├── openai_provider.py      # GPT-4o, etc.
│   │   │   │   ├── ollama_provider.py      # Local models
│   │   │   │   └── copilot_provider.py     # GitHub Copilot
│   │   │   ├── search_service.py      # Full-text + semantic search
│   │   │   ├── citation_service.py    # Source links & deep-link generation
│   │   │   └── storage_service.py     # File I/O for raw/wiki/converted
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── markdown_utils.py      # Frontmatter parsing, link helpers
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_classes.py
│   │   ├── test_files.py
│   │   ├── test_wiki_engine.py
│   │   ├── test_video_processor.py
│   │   └── test_chat.py
│   ├── alembic/                       # DB migrations (Alembic)
│   ├── pyproject.toml
│   └── requirements.txt
│
├── frontend/
│   ├── lib/
│   │   ├── main.dart                  # App entry point
│   │   ├── app.dart                   # MaterialApp + routing
│   │   ├── config/
│   │   │   └── theme.dart             # App theme (dark/light)
│   │   ├── models/
│   │   │   ├── hypatia_class.dart     # Class model
│   │   │   ├── wiki_page.dart         # Wiki page model
│   │   │   ├── source_file.dart       # Uploaded file model
│   │   │   └── chat_message.dart      # Chat message model
│   │   ├── services/
│   │   │   ├── api_client.dart        # HTTP client to backend
│   │   │   ├── websocket_service.dart # WebSocket for chat
│   │   │   └── file_picker_service.dart
│   │   ├── providers/
│   │   │   ├── class_provider.dart    # Current class state
│   │   │   ├── wiki_provider.dart     # Wiki tree + page state
│   │   │   ├── chat_provider.dart     # Chat messages state
│   │   │   └── file_provider.dart     # File list state
│   │   ├── screens/
│   │   │   └── home_screen.dart       # Main 3-panel layout
│   │   └── widgets/
│   │       ├── sidebar/
│   │       │   ├── sidebar.dart       # Left panel container
│   │       │   ├── class_dropdown.dart
│   │       │   ├── wiki_tree.dart     # Expandable file/wiki tree
│   │       │   ├── search_bar.dart
│   │       │   └── add_file_button.dart
│   │       ├── wiki_viewer/
│   │       │   ├── wiki_viewer.dart   # Center panel container
│   │       │   ├── markdown_renderer.dart
│   │       │   └── citation_link.dart # Clickable source citations
│   │       └── chat_panel/
│   │           ├── chat_panel.dart    # Right panel container
│   │           ├── message_bubble.dart
│   │           ├── command_input.dart  # Input with /command parsing
│   │           └── starter_cards.dart  # Quick-action cards
│   ├── test/
│   ├── pubspec.yaml
│   └── analysis_options.yaml
│
├── data/                              # Default: ~/.hypatia/data/ (configurable)
│   └── classes/
│       └── {class_id}/
│           ├── raw/                   # Original uploaded files
│           ├── converted/             # MarkItDown / transcript output
│           ├── wiki/                  # LLM-generated wiki pages
│           │   ├── index.md
│           │   ├── log.md
│           │   └── pages/
│           └── thumbnails/            # Preview images
│
├── docs/
│   ├── plan/                          # This planning directory
│   ├── api-contract.yaml              # OpenAPI spec (shared contract)
│   ├── llm-wiki.md
│   └── ui.png
│
├── spikes/                            # Phase 0.5 validation scripts (not shipped)
│   ├── faster_whisper_test.py
│   ├── llm_parsing_test.py
│   └── flutter_subprocess/
│
├── scripts/
│   ├── setup.sh                       # Dev environment setup
│   └── run_dev.sh                     # Start both backend + frontend
│
├── README.md
├── .gitignore
└── CLAUDE.md                          # Agent instructions for this repo
```

### Per-Class Data Directory Structure

Each Class gets an isolated data directory. This is critical to the requirement that Classes are independent and don't reference each other:

```
data/classes/{class_id}/
├── raw/                           # Immutable uploaded source files
│   ├── lecture-1.mp4
│   ├── chapter-3-notes.pdf
│   └── slides-week-2.pptx
├── converted/                     # Machine-readable conversions
│   ├── lecture-1.md               # Transcript with timestamps
│   ├── lecture-1.metadata.json    # Duration, frame count, etc.
│   ├── chapter-3-notes.md         # MarkItDown output
│   └── slides-week-2.md           # MarkItDown output
├── wiki/                          # LLM-generated wiki (git-initialized)
│   ├── .git/                      # Local git repo for version history
│   ├── schema.md                  # Wiki conventions for this Class
│   ├── index.md                   # Page catalog with summaries
│   ├── log.md                     # Chronological activity log
│   └── pages/
│       ├── source-summaries/      # One page per ingested source
│       │   ├── lecture-1.md
│       │   ├── chapter-3-notes.md
│       │   └── slides-week-2.md
│       ├── concepts/              # LLM-extracted concept pages
│       │   ├── neural-networks.md
│       │   └── backpropagation.md
│       └── entities/              # Named entities (people, tools, etc.)
│           └── geoffrey-hinton.md
└── thumbnails/                    # Preview images for files
```

---

## Key Architectural Decisions

### 1. Monorepo with separate backend/frontend
**Decision**: Single repository with `backend/` and `frontend/` directories.
**Rationale**: Simplifies development, allows shared documentation and scripts, keeps versioning in sync. The backend and frontend are deployed independently but developed together.

### 2. SQLite for the database
**Decision**: SQLite as the primary database, with FTS5 extension for full-text search.
**Rationale**: Zero configuration, file-based (portable), sufficient for a single-user/local application. Supports FTS5 for search. If multi-user/cloud deployment is needed later, migration to PostgreSQL is straightforward via SQLAlchemy.

### 3. Class isolation via filesystem
**Decision**: Each Class gets its own directory tree under `data/classes/{class_id}/`.
**Rationale**: Ensures complete independence between Classes. No cross-Class data leakage. Easy to backup, export, or delete a Class. The wiki engine operates within a single Class directory and has no visibility into other Classes.

### 4. LLM provider abstraction
**Decision**: Abstract LLM calls behind a `LLMService` interface that supports four providers: **OpenAI, Anthropic (Claude), Ollama, and GitHub Copilot**. Default provider is **Claude (Anthropic)**.
**Rationale**: Users should be able to choose their LLM provider. The wiki engine calls the abstraction, not a specific provider SDK. Claude is the default because of its strong long-context reasoning and structured output capabilities.

### 5. MarkItDown for document conversion
**Decision**: Use Microsoft's MarkItDown library for converting documents (PDF, DOCX, PPTX, XLSX, images) to markdown.
**Rationale**: Well-maintained, supports all major formats, produces LLM-friendly markdown. Handles the "raw source -> readable text" conversion that feeds into the wiki engine.

### 6. ffmpeg + faster-whisper for video
**Decision**: Custom video processing pipeline using ffmpeg for audio extraction and **`faster-whisper`** (CTranslate2 backend) for transcription.
**Rationale**: ffmpeg is the standard for audio/video manipulation. `faster-whisper` provides ~4x faster transcription than `openai-whisper` on CPU, with the same accuracy. Supports CUDA GPU acceleration. Unlike watch-skill's full pipeline, we only need: extract audio -> transcribe with timestamps -> produce searchable markdown.

### 7. Flutter with Riverpod for state management
**Decision**: Use Riverpod for state management in the Flutter frontend.
**Rationale**: Type-safe, testable, supports async state well (needed for API calls and WebSocket streams). Better than Provider for complex state graphs. Alternatives: Bloc (more boilerplate), Provider (less powerful).

### 8. WebSocket for chat streaming
**Decision**: WebSocket connection for real-time chat with the LLM, REST for everything else.
**Rationale**: LLM responses should stream token-by-token for good UX. WebSocket handles this naturally. All non-streaming operations (CRUD, file upload, wiki browsing) use standard REST.

### 9. Citations with deep links
**Decision**: Every fact extracted from a source file includes a citation that links to the exact location in the original file.
**Rationale**: Core requirement. For text documents, this means page/section references. For videos, this means timestamps. The citation format in wiki pages uses a structured syntax that the frontend can parse into clickable links.

### 10. User-editable wiki pages
**Decision**: Allow users to manually edit wiki pages. User edits are tracked separately and preserved during LLM rebuilds.
**Rationale**: Users may want to correct LLM mistakes or add annotations. User-edited sections are marked so the LLM merges around them during `/rebuild`, preventing overwrite.

### 11. Backend auto-launch
**Decision**: The Flutter app spawns the FastAPI backend process automatically on launch and manages its lifecycle (start on open, kill on close).
**Rationale**: Better UX than requiring the user to start the backend manually. The app starts `uvicorn` as a child process.

### 12. Data directory
**Decision**: Default data directory is `~/.hypatia/data/`, configurable in settings.
**Rationale**: User home directory is standard for app data. Keeps data separate from the project source. Configurable for users who want data elsewhere.

### 13. File size limit
**Decision**: Initial upload limit of **3GB**. Subject to change in future phases.
**Rationale**: Video lectures can be 1-5GB. 3GB covers most use cases. Chunked upload ensures large files don't cause memory issues.

### 14. Desktop-first
**Decision**: Target desktop platforms (Windows, macOS, Linux) first. Mobile layout is a future phase.
**Rationale**: The 3-panel layout is designed for desktop. Mobile would need a significantly different layout (tabbed/drawer-based) and is deferred.

### 15. Wiki versioning via git
**Decision**: Each Class's `wiki/` directory is a local git repository. Every wiki-modifying operation (ingest, rebuild, remove, user edit) auto-commits with a descriptive message.
**Rationale**: Provides free undo/history, diff visibility, and the ability to revert bad LLM generations. No remote push needed — purely local version control. Users can inspect history via the app or `git log` directly.

### 16. LLM context budget
**Decision**: Every LLM call has an explicit context budget: schema + index always included (~10% of context), source content capped at ~50%, existing wiki pages capped at ~30%, leaving ~10% for output. Context page selection uses FTS5 relevance ranking.
**Rationale**: Without a budget, large wikis (50+ pages) or large source documents will exceed context limits and either fail or produce low-quality output. The budget ensures predictable behavior regardless of wiki size.

### 17. Graceful degradation without LLM
**Decision**: Features are split into LLM-dependent (ingest, /ask, /summarize, /lint, /rebuild) and LLM-independent (wiki browsing, search, file viewing, /export, /remove, settings). LLM-independent features work fully when the provider is unavailable.
**Rationale**: Users should always be able to read their wiki and access their files, even when offline, rate-limited, or between API key rotations. The app should never feel "broken" due to a transient LLM issue.

### 18. Secure credential storage
**Decision**: API keys and secrets are stored in platform-native credential managers (Windows Credential Manager, macOS Keychain, Linux Secret Service) via the `keyring` library. Never in plaintext config files.
**Rationale**: API keys are high-value targets. Plaintext storage in dotfiles or config is a common security anti-pattern. Platform-native stores provide OS-level encryption and access control with no extra user burden.

### 19. Database migrations via Alembic
**Decision**: Use Alembic for all database schema changes from day one. The app auto-runs pending migrations on startup.
**Rationale**: Even for SQLite, schema evolution is inevitable. Starting with Alembic prevents the "we should have set this up earlier" problem. Auto-run on startup means users never need to run migration commands manually.

### 20. Dependency pinning with lockfiles
**Decision**: Direct dependencies use version-range constraints in `pyproject.toml`. A generated lockfile (`requirements.lock` via `pip-compile` or `uv lock`) pins exact versions for reproducible builds. Monthly update cadence.
**Rationale**: Reproducible builds prevent "works on my machine" issues. Version ranges allow security patches within a major version while the lockfile ensures everyone gets identical installs.

### 21. Dry-run preview for destructive operations
**Decision**: Destructive commands (`/rebuild`) default to a dry-run preview showing what will change before executing. Users must explicitly confirm after seeing the preview.
**Rationale**: `/rebuild` deletes and regenerates the entire wiki — an irreversible operation that costs money. Showing a preview first (pages to create/delete/update, estimated cost) gives users confidence and prevents expensive mistakes.

---

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Video transcription is slow (Whisper) | Poor UX for large lectures | High | Run transcription async with progress reporting. Consider offering quality tiers (tiny/base/small model). |
| LLM costs for wiki generation | May deter usage | Medium | Support local models via Ollama. Cache and reuse wiki pages. Batch operations to reduce API calls. Cost estimation before expensive operations. |
| Large file uploads (>1GB videos) | Memory/timeout issues | High | Chunked upload with progress. Stream files to disk, don't buffer in memory. |
| Cross-platform file path handling | Bugs on Windows vs macOS vs Linux | Medium | Use `pathlib` on backend, normalize paths. Test on all platforms. |
| Wiki consistency after /remove | Orphaned references, broken links | Medium | Implement a cleanup pass that finds and patches all references to removed sources. |
| LLM context window limits | Can't process very large documents in one pass | Medium | Explicit context budget strategy. Chunk large documents. Summarize chunks incrementally. |
| SQLite concurrent access | Issues if multiple tabs/instances | Low | Single-writer with WAL mode. This is a single-user app, so contention is minimal. |
| Concurrent file uploads overwhelm LLM | Rate limits hit, partial failures | Medium | Ingestion queue processes files sequentially. Queue position visible in UI. |
| LLM unavailable (bad key, rate limited) | App feels broken | Medium | Graceful degradation — browsing/search/export work without LLM. Clear error messages for LLM-dependent features. |

---

## Assumptions

1. **Single user, local deployment** — Hypatia runs on the user's machine. No multi-user auth needed initially.
2. **LLM API key required** — Users must provide their own API key (or run a local model via Ollama). Default provider is Claude (Anthropic).
3. **ffmpeg must be installed** — The video processing pipeline requires ffmpeg on the system PATH.
4. **Desktop-first** — The 3-panel layout targets desktop (Windows, macOS, Linux). Mobile layout is a future phase.
5. **English-first** — Initial transcription and wiki generation targets English. Multilingual support can be added later via faster-whisper's language parameter.
6. **Internet required for cloud LLMs** — Offline mode only works with local models (Ollama).
7. **Data lives in user home** — Default `~/.hypatia/data/`, configurable in settings.
8. **3GB upload limit** — Initial file size cap, subject to change.
9. **Backend auto-launches** — Flutter app manages the FastAPI process lifecycle.

---

## Open Questions

See [open-questions.md](./open-questions.md) for the full list of questions that need answers before or during implementation.
