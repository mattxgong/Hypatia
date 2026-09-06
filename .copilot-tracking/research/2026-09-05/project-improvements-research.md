<!-- markdownlint-disable-file -->

## Scope

Implement the prioritized findings from the 2026-09-05 whole-project review.
The current worktree contains unrelated user changes, including native Ollama
support. Preserve those changes and build on them.

## Confirmed Findings

* Provider dialogs submit masked credentials as real secrets
* Empty credential updates do not delete persisted credentials
* Backup imports lose file provenance IDs and can leave partial state
* Backup imports lack expanded-size and archive-entry limits
* Desktop build artifacts do not contain a runnable backend
* Chat starter cards are visible but have empty callbacks
* Python discovery accepts unsupported Python 3.10
* Panel sizing can starve the center wiki view
* Class and settings schemas lack useful input bounds
* Integration tests miss the highest-risk workflows
* Ollama, Windows setup, frontend, API, and licensing documentation has drifted

## Selected Approach

Implement safety-critical state transitions first, with focused regression
tests after each change. Follow with UI and launcher changes, then packaging and
documentation. Keep the local single-user architecture and existing framework
choices.

## Validation Baseline

* Backend Ruff, formatting, mypy, and 360 non-integration tests pass
* Frontend analysis, formatting, and 13 tests pass
* Backend WebSocket tests emit four unawaited AsyncMock warnings

## Licensing Follow-up

* No license, SPDX declaration, or historical licensing policy existed
* The package configuration prevents publication but does not establish rights
  for repository recipients
* The user selected Apache-2.0 and `Copyright 2026 Matthew Gong`
* Apache guidance calls for the canonical `LICENSE` text and recommends a
  `NOTICE` file; distributed derivatives must retain both when present

## Dependency License Follow-up

* No About dialog, `LicensePage`, or `LicenseRegistry` UI existed
* Class settings are unavailable before the first Class is created, so legal
  notices require a global entry point
* Flutter compiles dependency notices into `flutter_assets/NOTICES.Z` and its
  built-in About dialog opens a registry-backed license page
* The portable release check must search recursively because macOS nests
  Flutter assets inside the application bundle

## Development Startup Follow-up

* `scripts/run_dev.sh` starts a reload-enabled backend on port 8000, while the
  Flutter launcher previously treated that occupied port as a reason to start
  another backend on a free port
* A compile-time `HYPATIA_BACKEND_URL` value can transfer the script-owned URL
  to Flutter without changing packaged application behavior
* A configured external URL must imply connect-only ownership during startup
  and shutdown; Flutter may health-check the process but must not unload its
  Ollama model or terminate it
* Direct `flutter run` receives no external URL and retains the existing
  application-owned backend lifecycle
