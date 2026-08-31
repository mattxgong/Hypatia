# Phase 8: Integration & Polish

**Goal**: Complete deferred work from earlier phases, then test, harden, polish, and package the application for release. This is the final phase — its output is a stable, tested, cross-platform desktop application.

**Prerequisites**: Phases 1-6 functionally complete. Phase 7 substantially complete (verification in task 8.1).

**Outputs**: A release-ready application with end-to-end tests, cross-platform support, secure credential storage, performance benchmarks, polished UI, and desktop distribution builds.

**Note**: This phase absorbs deferred items from Phase 6 (backup/tasks frontend integration, class stats) and verifies Phase 7 completion (upload progress, drag-drop, source viewer media support). The original 8-task stub has been expanded to 10 tasks organized into three tracks.

---

## What Already Exists

These were delivered in earlier phases and do **not** need to be rebuilt:

- **Settings infrastructure**: `settings_provider.dart`, `settings.py` router, `provider_config_dialog.dart`, `provider_selector.dart`, `class_settings_screen.dart` — provider selection and basic config are wired up.
- **Backend routers for backup/tasks**: `backend/app/routers/backup.py` (backup/import endpoints), `backend/app/routers/tasks.py` (task status endpoints) — backend is done, frontend is not wired.
- **CI workflows**: `ci.yml` (lint + unit tests), `nightly.yml` (integration tests), `manual.yml` (desktop builds) — no E2E coverage yet.
- **Backend test suite**: ~30 test files including `test_api_integration.py` — but no true end-to-end harness.
- **Frontend tests**: 3 widget tests (`chat_panel_test`, `sidebar_test`, `widget_test`) — no integration tests.
- **Phase 7 packages**: `desktop_drop`, `media_kit`, `media_kit_video`, `media_kit_libs_windows`, `pdfrx` are in `pubspec.yaml`.

---

## Tasks

### Track A: Complete & Verify

### 8.1 Complete deferred work from Phases 6-7

Finish items explicitly deferred from earlier phases before testing or polishing.

**Backup/import frontend integration** (deferred from Phase 6):
- Wire `api_client.dart` methods for `POST /api/classes/{class_id}/backup` and `POST /api/classes/import` to UI actions.
- Add "Export Class" and "Import Class" options to the class dropdown menu or a class context menu.
- Export: trigger download of the backup ZIP. Import: open file picker for a `.zip`, upload, show progress, add the new class to the list.

**Tasks API frontend integration** (deferred from Phase 6):
- Wire `api_client.dart` task methods (`GET /api/classes/{class_id}/tasks`) to a UI indicator.
- Show active background tasks (rebuild, large ingest) as a small status badge in the sidebar or a non-modal notification bar.
- Poll while tasks are active; stop polling when idle.

**Class stats in dropdown** (deferred from Phase 6):
- Show file count and wiki page count alongside each class name in the class dropdown.
- Backend already returns stats from `GET /api/classes/{class_id}`; fetch stats when the dropdown opens.

**Verify Phase 7 UX items**:
- **Upload progress UI (7.6)**: Confirm real-time progress percentage displays during upload. Test multi-file upload with aggregate/per-file state. Test cancel.
- **Drag-and-drop upload (7.7)**: Confirm `DropTarget` overlay appears on hover, dropping valid files triggers upload with progress, invalid files are rejected with a snackbar.
- **Source viewer media support (7.8)**: Confirm `media_kit` plays video files and seeks to timestamp from citations. Confirm `pdfrx` renders PDFs and jumps to page from citations. Confirm image viewer with zoom/pan works.
- Fix any remaining wiring gaps found during verification.

**Acceptance**: All Phase 6/7 deferred items are implemented and functional. Backup round-trips (export → import) preserve all data. Task status is visible during long operations. Source viewer opens correct media for each file type.

---

### Track B: Testing

### 8.2 End-to-end testing

Write E2E tests that exercise the full stack (Flutter → API → backend services → database).

**Backend E2E harness**:
- Create `backend/tests/e2e/` directory with shared fixtures:
  - `conftest.py`: temporary data directory, temporary SQLite database, `httpx.AsyncClient` bound to the FastAPI app, WebSocket test helpers, cleanup on teardown.
  - Mock LLM provider (deterministic responses) for structural tests; real LLM for prompt regression (marked `@pytest.mark.integration`).

**Frontend integration tests**:
- Create `frontend/integration_test/` directory.
- Use Flutter's `integration_test` package with the `IntegrationTestWidgetsFlutterBinding`.
- Tests launch the real app (configured to point at a test backend instance).

**10 E2E scenarios**:

1. **First-time user flow** — App launches, backend auto-starts, create a class, upload a PDF, wait for processing, browse the generated wiki, ask a question, verify answer has citations.
2. **Multi-file ingestion** — Upload 3 different file types (PDF, DOCX, video), verify all are processed, wiki pages cross-reference between sources.
3. **/summarize** — Upload sources, run /summarize, verify a new synthesis page is created and indexed.
4. **/remove** — Upload a file, ingest it, then /remove it. Verify raw file, converted file, and wiki pages are cleaned up. Verify surviving pages have references stripped.
5. **Class isolation** — Create two classes, upload different files to each. Verify queries in one class don't return content from the other.
6. **User edits** — Edit a wiki page, run /rebuild, verify user edits are preserved in the regenerated wiki.
7. **/lint** — Upload sources with conflicting information, run /lint, verify contradictions are detected.
8. **/export** — Build a wiki from multiple sources, run /export, verify the ZIP contains all pages with correct structure.
9. **Backend lifecycle** — Launch app (backend auto-starts), close app (backend stops), relaunch (backend restarts). Verify data persistence across restart.
10. **Prompt regression** — Run the golden test corpus (from Phase 3B.10) against the current prompts and LLM provider. Verify structural consistency of output.

**CI integration**:
- Add an E2E job to `manual.yml` (workflow_dispatch) and `nightly.yml`.
- LLM-dependent E2E tests use `@pytest.mark.integration` (nightly only, not PR CI).
- Mock-LLM structural tests run in the standard `ci.yml` pipeline.

**Acceptance**: All 10 E2E scenarios pass. No cross-class data leakage. CI can run them on demand.

---

### 8.3 Cross-platform testing

Test the app on all three target desktop platforms.

- **Windows** (primary development platform):
  - Verify file paths use correct separators (`pathlib` usage).
  - Test file picker, drag-and-drop, backend subprocess management (`BackendLauncher`).
  - Verify `media_kit` video playback and `pdfrx` PDF rendering with Windows-specific native libraries.
  - Test Windows Credential Manager integration (task 8.7).

- **macOS**:
  - Verify app bundle (`.app`) builds and launches.
  - Test file permissions (sandbox vs. non-sandboxed).
  - Verify macOS Keychain integration for secure credential storage.
  - Test menu bar integration.
  - Verify `media_kit` and `pdfrx` native deps on macOS.

- **Linux**:
  - Verify dependency detection (ffmpeg, faster-whisper) with helpful error messages.
  - Test on common distros (Ubuntu 22.04+, Fedora).
  - Test X11 and Wayland compatibility for drag-and-drop (`desktop_drop`).
  - Verify Secret Service (GNOME Keyring / KDE Wallet) integration.

- Create a cross-platform checklist at `docs/cross-platform-checklist.md` documenting results.
- Fix platform-specific bugs discovered during testing.

**Acceptance**: App runs correctly on Windows, macOS, and Linux. Checklist completed for all three platforms.

---

### Track C: Polish & Ship

### 8.4 Performance optimization

Identify and fix performance bottlenecks against concrete, measurable targets.

**Performance targets** (automated benchmarks must assert these):

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
- Create benchmark tests in `backend/tests/benchmarks/` that assert the backend-side targets.
- Profile Python import time (target < 2s). Lazy-load heavy modules (`sentence-transformers`, `faster-whisper`, `markitdown`).
- Test wiki page rendering with large markdown pages (>10,000 words). Optimize Flutter markdown rendering if needed.
- Test FTS5 + hybrid search with 500+ wiki pages. Measure and tune query time.
- Verify chunked file upload — no in-memory buffering of full files.
- Verify async video processing doesn't block the API event loop. Test with a 2-hour lecture video.
- Profile chat streaming — verify token-by-token delivery doesn't lag or drop tokens.
- Add benchmark assertions to nightly CI (`nightly.yml`).

**Acceptance**: All performance targets met. App remains responsive during heavy operations. No UI freezes. Benchmarks enforced in CI.

---

### 8.5 Error handling hardening

Audit and strengthen error handling across the entire stack.

**Error categories to harden**:
- **Network errors**: Backend unreachable, timeout, connection reset. Show clear message, offer retry.
- **LLM errors**: API key invalid, rate limited, context too long, provider down. Surface actionable errors (e.g., "Check your API key in Settings" or "Try a shorter query").
- **File processing errors**: Corrupt file, unsupported format, ffmpeg crash, disk full. Report with details in the file status UI.
- **Database errors**: Locked database, migration failure, corrupt DB. Show recovery guidance.
- **WebSocket errors**: Disconnection during streaming. Save partial response, show reconnection indicator (exponential backoff already implemented).
- **Concurrent access**: Multiple app instances. Detect via SQLite lock and show a warning.

**Implementation**:
- Create a structured error catalog in `backend/app/utils/errors.py` with error codes, HTTP status mappings, and user-facing message templates.
- Audit every `try/except` block in the backend — ensure no bare `except:` or swallowed exceptions.
- Frontend: audit every `AsyncValue.when()` error branch — ensure each shows a user-visible message with an action (retry, navigate to settings, dismiss).
- **Graceful degradation audit**: Systematically verify that all LLM-independent features (wiki browsing, search, file viewing, /export, /remove, settings) work when the LLM provider is unavailable.
- Add structured logging (`structlog`) for every error path that doesn't already have it.

**Acceptance**: Every error path produces a user-visible, actionable message. No unhandled exceptions reach the user. Graceful degradation works for all LLM-independent features.

---

### 8.6 UI polish

Refine the visual design and interaction quality for a professional feel.

- **Consistency**: Audit spacing, typography, and color usage across all three panels. Ensure consistent padding, font sizes, and divider styles.
- **Animations**: Smooth transitions for panel resizing, page navigation, list item add/remove. Use Flutter's `AnimatedContainer`, `AnimatedSwitcher`, `SlideTransition` where appropriate.
- **Loading states**: Replace blank spaces with shimmer/skeleton loading indicators for wiki tree, file list, wiki page content, and search results.
- **Keyboard shortcuts**:
  - `Ctrl+K` / `Cmd+K` — focus search bar.
  - `Ctrl+N` / `Cmd+N` — new class dialog.
  - `Ctrl+Enter` — send chat message.
  - `Esc` — close dialogs, clear search, exit edit mode.
  - Display shortcut hints in tooltips.
- **Tooltips**: Add tooltips to every icon button (add files, new conversation, edit page, rebuild, settings, etc.).
- **Accessibility**:
  - Semantic labels for screen readers on all interactive elements.
  - Full keyboard navigation (tab order, focus indicators).
  - WCAG AA contrast ratios for all text and interactive elements.
- **Empty state refinement**: Review all empty states (no classes, no files, empty wiki, empty chat) for clarity and visual appeal.
- **Responsive panels**: Enforce minimum widths for each panel. Graceful collapse behavior when window is narrow.

**Acceptance**: UI feels polished and professional. No visual glitches or misaligned elements. Keyboard navigation works throughout the app.

---

### 8.7 Configuration and settings UI

Extend the existing settings infrastructure with secure credential storage, whisper configuration, and cost tracking.

**Secure credential storage** (architectural decision #18):
- **Backend (Python)**: Integrate the `keyring` library to store API keys in platform-native credential stores:
  - Windows: Windows Credential Manager.
  - macOS: Keychain.
  - Linux: Secret Service (GNOME Keyring / KDE Wallet).
- Add `keyring>=25.0.0` to `backend/pyproject.toml`.
- **Fallback**: If no platform credential store is available (headless Linux, CI), fall back to an encrypted file in `~/.hypatia/` with a user-provided passphrase. Show a clear warning that this is less secure.
- **Frontend**: Add `flutter_secure_storage` to `pubspec.yaml` for any client-side secrets.
- **Migration**: On first launch after upgrade from plaintext storage, auto-migrate existing keys to secure storage and delete the plaintext copies.
- Non-secret settings (theme, model size, data directory) remain in plaintext config.

**Settings UI additions** (extend existing `class_settings_screen.dart` and `provider_config_dialog.dart`):
- **LLM configuration**: Provider selection (already exists), API key input (store securely), model selection. Validate API key on entry (test LLM call → green check or error).
- **Provider switching UX**: When the user changes provider, show a notification: "Wiki was generated with [old provider]. Consider running /rebuild to regenerate with [new provider] for consistent quality."
- **Whisper configuration**: Model size selector (tiny / base / small / medium), device toggle (CPU / GPU).
- **Data directory**: Display current path (`~/.hypatia/data/`), option to change with data migration.
- **File size limit**: Display current limit (3GB), option to change.
- **Theme**: Verify dark/light toggle (already scaffolded in Phase 5.8).
- **Cost tracking**: Show cumulative token usage and estimated cost for the current billing period. Display per-operation estimates before expensive commands (/rebuild). Configurable monthly spend cap (default: off) — when reached, LLM-dependent features are disabled with a clear message.

**Acceptance**: Settings are configurable and persist across restarts. API keys are stored securely via platform-native credential storage. API key validation works. Cost estimates are shown for expensive operations.

---

### 8.8 Documentation

Write user-facing documentation.

- **README.md**: Rewrite with project overview, screenshots, installation prerequisites (Python 3.11+, Flutter SDK, ffmpeg), step-by-step quick start, supported file formats, command reference.
- **CLAUDE.md**: Review and update for Phase 8 changes (new dependencies, new settings, credential storage details).
- **In-app help**:
  - Tooltips on all interactive elements.
  - Command reference accessible from the chat panel: list of `/ask`, `/summarize`, `/remove`, `/lint`, `/rebuild`, `/export` with examples and expected behavior.
  - "What's this?" help icons on complex settings.
- **Supported formats reference**: List all supported file types in README and in a help section within the app.
- **Troubleshooting guide**: Section in README or a separate `docs/troubleshooting.md` covering common issues:
  - ffmpeg not found.
  - LLM API key invalid or expired.
  - Port 8000 already in use.
  - Database locked.
  - Copilot CLI not installed (for default provider).

**Acceptance**: A new user can install and start using the app by following the README. In-app help covers all commands. Troubleshooting guide addresses the most common issues.

---

### 8.9 Build and distribution

Set up build configuration for desktop distribution.

**Desktop builds**:
- Windows: `flutter build windows` producing an `.exe`. Optionally MSIX packaging for Windows Store.
- macOS: `flutter build macos` producing an `.app` bundle. DMG packaging (unsigned initially; notarization deferred to a later release).
- Linux: `flutter build linux` producing a binary. AppImage packaging for distribution.

**Backend bundling** (phased approach):
- **MVP (this phase)**: Ship backend as a Python package. Users install Python 3.11+ and run `scripts/setup.sh` (creates venv, installs deps). The Flutter app spawns `uvicorn` via `BackendLauncher` (already implemented in Phase 1, Task 1.9). This is the simplest approach and matches the current dev workflow.
- **Future**: PyInstaller single-executable bundling (no Python install needed). Larger binary but zero-config for end users.
- **Future**: Docker container option for advanced/server users.

**Build CI**:
- Update `manual.yml` to produce downloadable build artifacts for all 3 platforms.
- Add a build matrix: Windows (windows-latest), macOS (macos-latest), Linux (ubuntu-latest).

**Version stamping**:
- Define version in a single source of truth (`backend/app/__init__.py: __version__` and `frontend/pubspec.yaml: version`).
- Show version in the settings/about screen.

**Acceptance**: App can be built and distributed for Windows, macOS, and Linux. Backend starts automatically via `BackendLauncher`. Build artifacts are downloadable from CI.

---

### 8.10 Final integration verification

A dedicated verification pass after all other Phase 8 tasks are complete.

- Re-run all 10 E2E scenarios (8.2) on all three platforms (8.3).
- Re-run performance benchmarks (8.4) and verify all targets are met.
- Verify settings changes propagate correctly: change LLM provider → suggestion to /rebuild → rebuild works with new provider.
- Verify graceful degradation: disable LLM provider → confirm browse, search, export, remove, and settings all work.
- Verify wiki git versioning: ingest → edit → rebuild → check `git log` → revert to previous commit → verify rollback.
- Run the full quality check suite:
  ```bash
  # Backend
  cd backend
  ruff check .
  ruff format --check .
  mypy app
  pytest tests/ -m "not integration"

  # Frontend
  cd frontend
  flutter analyze
  dart format --set-exit-if-changed .
  flutter test
  ```
- Fix any remaining issues found during verification.

**Acceptance**: All checks pass. All E2E scenarios pass on all platforms. App is release-ready.

---

## Sequencing

```
8.1 (complete deferred) ──→ 8.2 (E2E tests) ──→ 8.3 (cross-platform)
                                              ──→ 8.4 (performance)
                                              ──→ 8.5 (error hardening)
8.6 (UI polish) — throughout, parallel with everything
8.7 (settings + credentials) — can start immediately, parallel with 8.1
8.8 (docs) — after features stable (after 8.1, 8.5, 8.7)
8.9 (build) — after 8.5 (error handling done)
8.10 (final verification) — last, after everything else
```

- **8.1 first** — complete deferred work before testing it.
- **8.2 after 8.1** — E2E tests need complete features to exercise.
- **8.3, 8.4, 8.5 in parallel after 8.2** — cross-platform, performance, and error hardening are independent tracks.
- **8.6 throughout** — UI polish is ongoing, applied incrementally alongside other tasks.
- **8.7 parallel with 8.1** — settings/credentials work is independent of deferred feature completion.
- **8.8 after 8.1 + 8.5 + 8.7** — documentation should reflect final feature set and error messages.
- **8.9 after 8.5** — build distribution should include hardened error handling.
- **8.10 last** — final verification is the gate to release.

---

## New Dependencies

**Backend** (`pyproject.toml`):
```toml
keyring>=25.0.0    # Platform-native credential storage
```

**Frontend** (`pubspec.yaml`):
```yaml
flutter_secure_storage: ^9.0.0    # Secure client-side secret storage
integration_test:                  # Flutter SDK integration testing (dev_dependency)
  sdk: flutter
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| Bundling Python backend with Flutter is complex | Start with separate processes (user installs Python). PyInstaller bundling is a future optimization after the MVP ships. |
| Cross-platform file path differences | Use `pathlib` consistently on backend, `path` package on frontend. Test on all platforms early (8.3). |
| Desktop build signing (macOS notarization, Windows signing) | Defer signing to a later release. Distribute unsigned initially with clear installation instructions. |
| `keyring` unavailable on headless Linux / CI | Implement encrypted-file fallback with passphrase. CI uses env vars, not keyring. |
| Provider switch degrades wiki quality | Settings UI recommends /rebuild after switch. Prompt regression tests (E2E scenario 10) verify structural output across providers. |
| `media_kit` / `pdfrx` native deps break on some platforms | These are already in `pubspec.yaml` and were tested during Phase 7. Cross-platform testing (8.3) catches remaining issues. Fall back to text viewer if native viewer fails. |
| E2E tests are slow and flaky | Separate mock-LLM structural tests (fast, run in CI) from real-LLM tests (slow, nightly only). Use deterministic test fixtures. |
| Git versioning adds overhead for large wikis | Auto-commits are fast for typical wikis. For large wikis (500+ pages), batch commits per operation rather than per-page. Monitor in performance benchmarks (8.4). |
| Performance targets too aggressive for CI runners | Benchmarks use relative thresholds where possible. Absolute targets tested on reference hardware; CI uses smoke tests (no regression from baseline). |
