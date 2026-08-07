# Phase 8: Integration & Polish

**Goal**: End-to-end testing, cross-platform verification, performance optimization, error hardening, and UX polish to bring the application to a releasable state.

**Prerequisites**: All previous phases (1-7) are functionally complete.

**Outputs**: A stable, tested, cross-platform application ready for use.

---

## Tasks

### 8.1 End-to-end testing
Write E2E tests that exercise the full stack (Flutter -> API -> backend services -> database):
- **Scenario 1: First-time user flow** — App launches, backend auto-starts, create a class, upload a PDF, wait for processing, browse the generated wiki, ask a question, verify answer has citations.
- **Scenario 2: Multi-file ingestion** — Upload 3 different file types (PDF, DOCX, video), verify all are processed, wiki pages cross-reference between sources.
- **Scenario 3: /summarize** — Upload sources, run /summarize, verify a new synthesis page is created and indexed.
- **Scenario 4: /remove** — Upload a file, ingest it, then /remove it. Verify raw file, converted file, and wiki pages are cleaned up. Verify surviving pages have references stripped.
- **Scenario 5: Class isolation** — Create two classes, upload different files to each. Verify queries in one class don't return content from the other.
- **Scenario 6: User edits** — Edit a wiki page, run /rebuild, verify user edits are preserved in the regenerated wiki.
- **Scenario 7: /lint** — Upload sources with conflicting information, run /lint, verify contradictions are detected.
- **Scenario 8: /export** — Build a wiki from multiple sources, run /export, verify the ZIP contains all pages with correct structure.
- **Scenario 9: Backend lifecycle** — Launch app (backend auto-starts), close app (backend stops), relaunch (backend restarts). Verify data persistence.
- **Scenario 10: Prompt regression** — Run the golden test corpus (from Phase 3B.10) against the current prompts and LLM provider. Verify structural consistency of output.
- Use Flutter integration tests for frontend. Use pytest for backend.

**Acceptance**: All E2E scenarios pass. No cross-class data leakage.

---

### 8.2 Cross-platform testing
Test the Flutter app on all target platforms:
- **Windows** — primary development platform. Verify file paths use correct separators. Test file picker.
- **macOS** — verify app bundle, file permissions, menu bar integration.
- **Linux** — verify dependencies (ffmpeg, whisper). Test on common distros.
- **Web** (if supported) — note limitations (no local file access, WebSocket differences).
- Fix platform-specific bugs (file path handling is the most common issue).

**Acceptance**: App runs correctly on Windows, macOS, and Linux.

---

### 8.3 Performance optimization
Identify and fix performance bottlenecks against concrete targets:

**Performance targets** (measurable thresholds — tests must assert these):
| Operation | Target | Measurement |
|-----------|--------|-------------|
| App startup (backend ready) | < 5 seconds | Time from Flutter launch to `/health` returning 200 |
| Wiki page render | < 100ms | Time from page data received to pixels on screen |
| Wiki tree load | < 200ms | Time to fetch and display sidebar tree for a 100-page wiki |
| FTS5 search (500 pages) | < 300ms | Query-to-results for a typical keyword search |
| File list load | < 200ms | API response time for `GET /api/classes/{id}/files` (50 files) |
| Chat first token | < 2 seconds | Time from send to first streamed token appearing (excludes LLM latency) |
| File upload start | < 500ms | Time from file selection to upload progress appearing |

**Optimization checklist**:
- **Large file upload**: Ensure chunked upload, no memory buffering of full file.
- **Video processing**: Verify async processing doesn't block the API. Test with a 2-hour lecture video.
- **Wiki page rendering**: Test with large markdown pages (>10,000 words). Optimize rendering if needed.
- **Search performance**: Test FTS5 with 500+ wiki pages. Measure query time.
- **Chat streaming**: Verify token-by-token streaming doesn't lag or drop tokens.
- **Startup time**: Measure app startup. Lazy-load heavy components. Profile Python import time (target < 2s for imports).

**Acceptance**: All performance targets are met. App remains responsive during heavy operations. No UI freezes. Targets are enforced via automated benchmarks in CI (can run as part of nightly builds).

---

### 8.4 Error handling hardening
Audit and strengthen error handling:
- **Network errors**: Backend unreachable, timeout, connection reset. Show clear messages, offer retry.
- **LLM errors**: API key invalid, rate limited, context too long, provider down. Surface actionable errors.
- **File processing errors**: Corrupt file, unsupported format, ffmpeg crash, disk full. Report with details.
- **Database errors**: Locked database, migration needed, corrupt DB. Recovery options.
- **Concurrent access**: Multiple tabs or instances. Graceful handling of conflicts.
- Add structured logging throughout the backend.

**Acceptance**: Every error path produces a user-visible, actionable message. No unhandled exceptions.

---

### 8.5 UI polish
Refine the visual design:
- Consistent spacing, typography, and color usage.
- Smooth animations for panel resizing, page transitions, list updates.
- Loading skeletons instead of blank spaces.
- Keyboard shortcuts: Ctrl+K for search, Ctrl+N for new class, Ctrl+Enter to send chat.
- Tooltips on all icon buttons.
- Accessibility: screen reader labels, keyboard navigation, sufficient contrast.

**Acceptance**: UI feels polished and professional. No visual glitches or misaligned elements.

---

### 8.6 Configuration and settings UI
Build a settings screen (accessible from sidebar):
- **LLM Configuration**: Provider selection (OpenAI / Anthropic / Ollama / GitHub Copilot), API key input, model selection. Default: Claude (Anthropic).
  - **Provider switching UX**: When user changes provider, show a notification: "Wiki was generated with [old provider]. Consider running /rebuild to regenerate with [new provider] for consistent quality." This is a suggestion, not a requirement — the wiki continues to work regardless.
- **Whisper Configuration**: Model size (tiny/base/small/medium), device (CPU/GPU). Uses faster-whisper.
- **Data Directory**: Show where data is stored (default `~/.hypatia/data/`), option to change.
- **File Size Limit**: Show current limit (3GB), option to change.
- **Theme**: Dark/light toggle.
- Persist settings to a local config file or database.
- Validate API key on entry (make a test call).
- **Secure credential storage** — API keys must never be stored in plaintext config files:
  - **Backend (Python)**: Use the `keyring` library to store API keys in the platform-native credential store:
    - Windows: Windows Credential Manager
    - macOS: Keychain
    - Linux: Secret Service (GNOME Keyring / KDE Wallet)
  - **Frontend (Flutter)**: Use `flutter_secure_storage` for any client-side secrets (e.g., cached auth tokens if needed).
  - **Fallback**: If no platform credential store is available (headless Linux), fall back to an encrypted file in `~/.hypatia/` with a user-provided passphrase, with a clear warning that this is less secure.
  - Non-secret settings (theme, model size, data directory) remain in a plaintext config file.
  - On first launch after upgrade from plaintext storage: auto-migrate existing keys to secure storage and delete the plaintext copies.
- **Cost tracking**: Show cumulative token usage and estimated cost for the current billing period. Display per-operation estimates before expensive commands (/rebuild). Configurable monthly spend cap (default: off) — when reached, LLM-dependent features are disabled with a clear message.

**Acceptance**: Settings are configurable and persist. API keys are stored securely via platform-native credential storage. API key validation works. Cost estimates are shown for expensive operations.

---

### 8.7 Documentation
Write user-facing documentation:
- **README.md** — project overview, installation instructions, quick start guide.
- **CLAUDE.md** — agent instructions for the repository.
- **Inline help** — tooltips and help text within the app.
- **Supported formats** — list of all file types that can be processed.
- **Command reference** — documentation for /ask, /summarize, /remove, /lint, /rebuild, /export within the app.

**Acceptance**: A new user can install and start using the app by following the README.

---

### 8.8 Build and distribution
Set up build configuration:
- **Desktop builds**: Flutter build for Windows (.exe / .msix), macOS (.app / .dmg), Linux (.deb / .AppImage).
- **Backend packaging**: The Flutter app auto-launches the backend (Phase 1, Task 1.9). For distribution, options:
  - Ship backend as a Python package (user installs Python + deps via setup script)
  - Bundle with PyInstaller (single executable, larger but no Python install needed)
  - Docker container (for advanced users)
- **Startup**: Flutter app manages backend lifecycle automatically. Loading screen shown while backend starts.
- **Auto-update**: Consider mechanism for future updates.

**Acceptance**: App can be built and distributed for at least one platform. Backend starts automatically.

---

## Sequencing

```
8.1 (E2E tests) ──→ 8.2 (cross-platform)
               ──→ 8.3 (performance)
               ──→ 8.4 (error hardening)
8.5 (UI polish) — throughout
8.6 (settings) — can be done anytime
8.7 (docs) — after features are stable
8.8 (build) — last
```

- 8.1 first (find bugs before optimizing).
- 8.2, 8.3, 8.4 can run in parallel after 8.1.
- 8.5 is ongoing throughout the phase.
- 8.6 is independent.
- 8.7 after features stabilize.
- 8.8 is last.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Bundling Python backend with Flutter is complex | Start with separate processes (user installs Python). PyInstaller bundling is a future optimization. |
| Cross-platform file path differences | Use `pathlib` consistently. Test on all platforms early. |
| Desktop build signing (macOS notarization, Windows signing) | Defer signing to a later release. Distribute unsigned initially. |
| Provider switch degrades wiki quality | Settings UI recommends /rebuild after switch. Prompt regression tests verify structural output across providers. |
| Git versioning adds overhead | Auto-commits are fast for small wikis. For large wikis (500+ pages), batch commits per operation rather than per-page. |
