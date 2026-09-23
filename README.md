<h1 align="center">Hypatia</h1>

<p align="center">
    <strong>Cross-platform desktop app for building persistent study wikis from course materials</strong>
</p>

[![CI](https://github.com/mattxgong/Hypatia/actions/workflows/ci.yml/badge.svg)](https://github.com/mattxgong/Hypatia/actions/workflows/ci.yml)

Hypatia is an LLM-powered study wiki builder. Upload lecture videos, notes,
PDFs, and slides, then browse, search, and chat with the interlinked knowledge base that Hypatia maintains.

## How It Works

Hypatia lets you create **Classes**, independent study wikis backed by their own
repositories of source material. When you upload files, the LLM reads and
synthesizes them into a persistent, interlinked wiki of Markdown pages. Unlike
RAG systems that derive answers from raw documents on every query, Hypatia
incrementally maintains this wiki so your knowledge base grows over time.

You interact with each Class through a chat interface that supports natural-language queries, summarization, and wiki management commands.

## Features

* **Multi-format ingestion**: Upload PDFs, DOCX, PPTX, XLSX, video, audio, images, Markdown, and plain text
* **LLM wiki generation**: Build interlinked wiki pages from your sources
* **Chat interface**: Ask questions, get cited answers, and run management commands
* **Full-text search**: Search all wiki pages through FTS5
* **Version history**: Track wiki revisions and roll back through Git
* **Multiple LLM providers**: Use GitHub Copilot, Copilot with Ollama, Anthropic, OpenAI, or native Ollama
* **Backup and restore**: Export and import complete Classes as ZIP archives
* **Cross-platform desktop app**: Run on Windows, macOS, and Linux

## Prerequisites

| Dependency | Version | Notes |
|------------|---------|-------|
| **Python** | 3.11+ | Backend runtime |
| **Flutter SDK** | Stable channel | Frontend framework |
| **ffmpeg** | Any recent | Required for audio/video transcription |
| **Git** | Any recent | Used for wiki version history |

Backend setup installs [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
for local audio and video transcription. A CUDA-capable GPU accelerates
transcription but is not required.

## Quick Start

### macOS and Linux setup

```bash
git clone https://github.com/mattxgong/Hypatia.git
cd Hypatia
./scripts/setup.sh
```

This creates the backend virtual environment, installs the exact dependency
versions pinned in `backend/requirements.lock`, and runs `flutter pub get`.

### Windows PowerShell setup

The repository setup scripts use Bash. Run these equivalent commands from
PowerShell on Windows:

```powershell
git clone https://github.com/mattxgong/Hypatia.git
Set-Location Hypatia
Set-Location backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
Set-Location ..\frontend
flutter pub get
Set-Location ..
```

If `py -3.11` is unavailable, use another installed Python executable that
reports version 3.11 or newer.

### Configure an LLM provider

Create `backend/.env` with your preferred provider:

```bash
# Option A: Anthropic
HYPATIA_LLM_PROVIDER=anthropic
HYPATIA_ANTHROPIC_API_KEY=sk-ant-...

# Option B: OpenAI
HYPATIA_LLM_PROVIDER=openai
HYPATIA_OPENAI_API_KEY=sk-...

# Option C: Ollama native API (local, no API key)
HYPATIA_LLM_PROVIDER=ollama
HYPATIA_OLLAMA_BASE_URL=http://localhost:11434
HYPATIA_LLM_MODEL=llama3.2

# Option D: GitHub Copilot (default, no config needed if Copilot CLI is installed)
```

For native Ollama, install and start Ollama separately, then download the model
before starting Hypatia:

```bash
ollama pull llama3.2
ollama serve
```

The Ollama desktop application may already run the server, in which case
`ollama serve` is unnecessary. Hypatia uses Ollama's native API, lists locally
installed models in Settings, sizes the context window from model metadata,
and asks Ollama to unload the active model when you switch providers or exit.

### Run on macOS or Linux

```bash
cd frontend
flutter run
```

### Run on Windows PowerShell

Start Flutter from the repository root:

```powershell
Set-Location frontend
flutter run
```

The Flutter desktop app locates the repository backend, selects a free port,
and launches it automatically. The same launcher behavior is used by packaged
desktop builds.

### Create your first Class

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

Maximum file size: 3 GB. Override it with
`HYPATIA_MAX_UPLOAD_SIZE_BYTES` before starting the backend.

File names must be unique within a Class. Uploading a name that already exists
is rejected with a conflict error; rename the file or remove the existing source
first. Uploads in one batch succeed or fail together, so a rejected file never
leaves the rest of its batch half-processed.

Removing a source cancels its conversion or wiki ingestion if either is still
running, then deletes its converted artifacts and the wiki pages built only
from it.

## Chat Commands

Type these in the chat panel to manage your Class wiki:

| Command | Description | Example |
|---------|-------------|---------|
| `/ask <query>` | Ask a question; the LLM answers from the wiki with citations | `/ask What is gradient descent?` |
| `/summarize <topic>` | Generate a new wiki summary page on a topic | `/summarize key concepts from lecture 3` |
| `/remove <filename>` | Remove a source file and clean up its wiki pages | `/remove lecture1.pdf` |
| `/lint` | Check the wiki for contradictions and structural issues | `/lint` |
| `/rebuild` | Regenerate the entire wiki from sources (long-running) | `/rebuild` |
| `/export` | Export the wiki as a collection of markdown files | `/export` |

You can also type plain text without a command prefix. This defaults to `/ask`.

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

Choose GitHub Copilot, Copilot with an Ollama backend, Anthropic, OpenAI, or
native Ollama. API keys are stored through the platform credential store
(Windows Credential Manager, macOS Keychain, or Linux Secret Service). If no
credential store is available, keys fall back to an access-restricted file in
`~/.hypatia/data/`. Native Ollama requires no API key.

**Environment variables** (set in `backend/.env` or your shell):

| Variable | Default | Description |
|----------|---------|-------------|
| `HYPATIA_DATA_DIR` | `~/.hypatia/data` | Database and file storage location |
| `HYPATIA_LOGS_DIR` | `~/.hypatia/logs` | Log file directory |
| `HYPATIA_LLM_PROVIDER` | `copilot` | LLM provider (`copilot`, `copilot-ollama`, `anthropic`, `openai`, or `ollama`) |
| `HYPATIA_LLM_MODEL` | Provider default | Model name override |
| `HYPATIA_ANTHROPIC_API_KEY` | Not set | Anthropic API key |
| `HYPATIA_OPENAI_API_KEY` | Not set | OpenAI API key |
| `HYPATIA_GITHUB_TOKEN` | Not set | Optional GitHub token for Copilot authentication |
| `HYPATIA_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `HYPATIA_WHISPER_MODEL_SIZE` | `base` | faster-whisper model size, including `tiny`, `base`, `small`, `medium`, and supported large or distil variants |
| `HYPATIA_WHISPER_DEVICE` | `cpu` | Whisper device: `cpu` or `cuda` |
| `HYPATIA_MAX_UPLOAD_SIZE_BYTES` | `3221225472` | Maximum uploaded file size in bytes |

### Data and logs

| Location | Contents |
|----------|----------|
| `~/.hypatia/data/hypatia.db` | SQLite database for Classes, files, wiki pages, and chat history |
| `~/.hypatia/data/classes/<class-id>/` | Uploaded sources, converted Markdown, and the Git-versioned wiki |
| `~/.hypatia/data/settings.json` | Non-secret settings saved from the Settings screen |
| `~/.hypatia/logs/hypatia.log` | Structured JSON backend log, rotated at 10 MB with five backups |

On Windows, `~` is your user profile directory, such as `C:\Users\<you>`.
The test suite writes its logs under `backend/.pytest_cache/logs/` and never
touches these directories.

## Packaged Desktop Builds

The manual GitHub Actions workflow produces Windows, macOS, and Linux desktop
artifacts. Each artifact contains the Flutter application plus the backend
source, Alembic migrations, and Python dependency manifests in a neighboring
`backend/` directory.

Python itself is not bundled. On first launch, the desktop app finds an
installed Python 3.11 or newer, creates `backend/.venv`, installs the exact
versions pinned in `backend/requirements.lock`, selects an available port from
8000 through 8010, and starts the FastAPI backend. The app records which lock
it installed and reinstalls automatically whenever a newer build ships a
different lock, so an existing environment never runs with stale dependencies.
Keep the artifact directory intact so the app can find its `backend/`
directory. Dependency installation requires network access.

Ollama, local model files, ffmpeg, and Git are also external prerequisites;
the desktop artifact does not install them.

## Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md) for solutions to common issues including:

* ffmpeg not found
* LLM API key invalid or expired
* Port 8000 already in use
* Database locked errors
* Copilot CLI not installed

## Development

See [CLAUDE.md](CLAUDE.md) for the full repository layout, architecture, coding conventions, and testing instructions.

For backend hot reload on macOS, Linux, or Git Bash, run:

```bash
./scripts/run_dev.sh
```

The script owns one Uvicorn process on port 8000 and passes its URL to Flutter
through `HYPATIA_BACKEND_URL`. In this mode, Flutter connects to that process
without launching or stopping another backend. A direct `flutter run` keeps the
normal application-managed backend behavior.

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

The fast backend run includes the end-to-end suite in `backend/tests/e2e/`,
which drives the real FastAPI app against a temporary data directory with a
mock LLM, including deleting files mid-conversion and mid-ingestion. Run it on
its own with `pytest tests/e2e/ -v`. Integration tests that call a real LLM are
marked `integration` and run nightly.

### Updating backend dependencies

`backend/requirements.lock` pins every backend package for all platforms, and
CI fails if it is out of date with `backend/pyproject.toml`. After changing a
dependency in `pyproject.toml`, regenerate the lock from `backend/`:

```bash
python -m uv pip compile pyproject.toml --extra dev --universal -o requirements.lock
```

Existing pins are kept unless the new constraints require a change. Reinstall
with `pip install -r requirements.lock` to update your environment.

## Architecture

```
Flutter Desktop App ←→ FastAPI Backend ←→ SQLite + File Storage
       (UI)              (API + LLM)        (Persistence)
```

* **Frontend**: Flutter desktop app with three-panel layout (sidebar, wiki viewer, chat panel)
* **Backend**: FastAPI with async SQLAlchemy, structlog logging, WebSocket chat
* **Database**: SQLite with Alembic migrations and FTS5 full-text search
* **Wiki versioning**: Per-Class Git repositories for full revision history
* **LLM abstraction**: Provider system for Copilot, Copilot with Ollama, Anthropic, OpenAI, and native Ollama

## License

Copyright 2026 Matthew Gong. Licensed under the
[Apache License, Version 2.0](LICENSE). See [NOTICE](NOTICE) for attribution.
In the desktop app, select the **About Hypatia** info icon and then
**View licenses** to inspect notices for bundled dependencies.
