<h1 align="center">Hypatia</h1>

<p align="center">
  <a href="https://github.com/mattxgong/Hypatia/actions/workflows/ci.yml"><img src="https://github.com/mattxgong/Hypatia/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

<p align="center">
  <strong>An LLM-powered study wiki builder. Upload your lecture videos, notes, PDFs, and slides — Hypatia builds and maintains an interlinked knowledge base you can browse, search, and chat with.</strong>
</p>

---

## How It Works

Hypatia lets you create **Classes** — independent study wikis, each backed by its own repository of source material. When you upload files, the LLM reads and synthesizes them into a persistent, interlinked wiki of markdown pages. Unlike RAG systems that re-derive answers from raw documents on every query, Hypatia incrementally builds and maintains this wiki so your knowledge base grows over time.

You interact with each Class through a chat interface that supports natural-language queries, summarization, and wiki management commands.

## Features

- **Multi-format ingestion** — Upload PDFs, DOCX, PPTX, XLSX, video, audio, images, markdown, and plain text
- **LLM wiki generation** — Automatically builds interlinked wiki pages from your sources
- **Chat interface** — Ask questions, get cited answers, run management commands
- **Full-text search** — FTS5-powered search across all wiki pages
- **Version history** — Git-backed wiki with full revision history and rollback
- **Multiple LLM providers** — GitHub Copilot (default), Anthropic, OpenAI, or Ollama
- **Backup/restore** — Export and import entire Classes as ZIP archives
- **Cross-platform** — Windows, macOS, and Linux desktop app

## Prerequisites

| Dependency | Version | Notes |
|------------|---------|-------|
| **Python** | 3.11+ | Backend runtime |
| **Flutter SDK** | Stable channel | Frontend framework |
| **ffmpeg** | Any recent | Required for audio/video transcription |
| **Git** | Any recent | Used for wiki version history |

Optional: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) is installed automatically for local audio/video transcription. A CUDA-capable GPU accelerates transcription but is not required.

## Quick Start

**1. Clone and set up:**

```bash
git clone https://github.com/mattxgong/Hypatia.git
cd Hypatia
scripts/setup.sh
```

This creates the backend virtual environment, installs all dependencies, and runs `flutter pub get`.

**2. Configure an LLM provider:**

Create `backend/.env` with your preferred provider:

```bash
# Option A: Anthropic
HYPATIA_LLM_PROVIDER=anthropic
HYPATIA_ANTHROPIC_API_KEY=sk-ant-...

# Option B: OpenAI
HYPATIA_LLM_PROVIDER=openai
HYPATIA_OPENAI_API_KEY=sk-...

# Option C: Ollama (local, free)
HYPATIA_LLM_PROVIDER=openai
HYPATIA_OPENAI_BASE_URL=http://localhost:11434/v1
HYPATIA_OPENAI_API_KEY=ollama
HYPATIA_LLM_MODEL=llama3

# Option D: GitHub Copilot (default, no config needed if Copilot CLI is installed)
```

**3. Run the app:**

```bash
scripts/run_dev.sh
```

This starts the backend API server on port 8000 and launches the Flutter desktop app. In normal use, the Flutter app auto-launches the backend — `run_dev.sh` is for development with backend hot-reload.

**4. Create your first Class:**

1. Click **+ New Class** in the sidebar
2. Upload source material (drag-and-drop or file picker)
3. Wait for processing to complete
4. Browse the generated wiki, search, or ask questions in chat

## Supported File Formats

| Format | Extensions | Processing |
|--------|-----------|------------|
| PDF | `.pdf` | Text extraction via MarkItDown |
| Word | `.docx` | Text extraction via MarkItDown |
| PowerPoint | `.pptx` | Slide text extraction |
| Excel | `.xlsx` | Table extraction |
| Video | `.mp4`, `.avi`, `.mov`, `.mkv` | ffmpeg + faster-whisper transcription |
| Audio | `.mp3`, `.wav`, `.m4a` | ffmpeg + faster-whisper transcription |
| Images | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` | Image viewer (no OCR) |
| Markdown | `.md`, `.markdown` | Passthrough (no conversion) |
| Plain text | `.txt` | Passthrough (no conversion) |
| CSV/HTML | `.csv`, `.html` | Extraction via MarkItDown |

Maximum file size: 3 GB (configurable in Settings).

## Chat Commands

Type these in the chat panel to manage your Class wiki:

| Command | Description | Example |
|---------|-------------|---------|
| `/ask <query>` | Ask a question — the LLM answers from the wiki with citations | `/ask What is gradient descent?` |
| `/summarize <topic>` | Generate a new wiki summary page on a topic | `/summarize key concepts from lecture 3` |
| `/remove <filename>` | Remove a source file and clean up its wiki pages | `/remove lecture1.pdf` |
| `/lint` | Check the wiki for contradictions and structural issues | `/lint` |
| `/rebuild` | Regenerate the entire wiki from sources (long-running) | `/rebuild` |
| `/export` | Export the wiki as a collection of markdown files | `/export` |

You can also type plain text without a command prefix — this defaults to `/ask`.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+K` | Focus the search bar (opens sidebar if collapsed) |
| `Ctrl+N` | Create a new class |
| `Ctrl+B` | Toggle the sidebar |
| `Ctrl+J` | Toggle the chat panel |
| `Escape` | Clear search / close dialogs |

## Configuration

Settings are accessible from the gear icon in the sidebar. Configuration is persisted across restarts.

**LLM provider**: Choose between GitHub Copilot, Anthropic, OpenAI, or Ollama. API keys are stored securely via your platform's native credential store (Windows Credential Manager, macOS Keychain, or Linux Secret Service). If no credential store is available, keys fall back to an access-restricted file in `~/.hypatia/`.

**Environment variables** (set in `backend/.env` or your shell):

| Variable | Default | Description |
|----------|---------|-------------|
| `HYPATIA_DATA_DIR` | `~/.hypatia/data` | Database and file storage location |
| `HYPATIA_LOGS_DIR` | `~/.hypatia/logs` | Log file directory |
| `HYPATIA_LLM_PROVIDER` | `copilot` | LLM provider (`copilot`, `anthropic`, `openai`) |
| `HYPATIA_LLM_MODEL` | Provider default | Model name override |
| `HYPATIA_ANTHROPIC_API_KEY` | — | Anthropic API key |
| `HYPATIA_OPENAI_API_KEY` | — | OpenAI API key |
| `HYPATIA_OPENAI_BASE_URL` | — | Custom OpenAI-compatible endpoint (e.g. Ollama) |
| `HYPATIA_WHISPER_MODEL_SIZE` | `base` | Whisper model: `tiny`, `base`, `small`, `medium` |
| `HYPATIA_WHISPER_DEVICE` | `cpu` | Whisper device: `cpu` or `cuda` |

## Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md) for solutions to common issues including:

- ffmpeg not found
- LLM API key invalid or expired
- Port 8000 already in use
- Database locked errors
- Copilot CLI not installed

## Development

See [CLAUDE.md](CLAUDE.md) for the full repository layout, architecture, coding conventions, and testing instructions.

**Run quality checks locally (same as CI):**

```bash
# Backend (from backend/)
ruff check .
ruff format --check .
mypy app
pytest tests/ -m "not integration"

# Frontend (from frontend/)
flutter analyze
dart format --set-exit-if-changed .
flutter test
```

## Architecture

```
Flutter Desktop App ←→ FastAPI Backend ←→ SQLite + File Storage
       (UI)              (API + LLM)        (Persistence)
```

- **Frontend**: Flutter desktop app with three-panel layout (sidebar, wiki viewer, chat panel)
- **Backend**: FastAPI with async SQLAlchemy, structlog logging, WebSocket chat
- **Database**: SQLite with Alembic migrations, FTS5 full-text search
- **Wiki versioning**: Per-class git repositories for full revision history
- **LLM abstraction**: Pluggable provider system (Copilot, Anthropic, OpenAI/Ollama)

## License

See [LICENSE](LICENSE) for details.
