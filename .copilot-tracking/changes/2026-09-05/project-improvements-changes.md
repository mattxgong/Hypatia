<!-- markdownlint-disable-file -->

## Related Plan

`.copilot-tracking/plans/2026-09-05/project-improvements-plan.instructions.md`

## Implementation Date

2026-09-05

## Summary

Completed the ordered project-improvement program across credential safety,
backup integrity, usability, validation, desktop distribution, integration
coverage, documentation, explicit open-source licensing, and development
backend ownership.

## Added

* Backend settings regression tests
* Flutter launcher, layout, input-validation, and credential widget tests
* Flutter workflow integration coverage with in-memory API and WebSocket seams
* Shared Flutter input validation helpers
* Canonical Apache-2.0 `LICENSE`
* Project `NOTICE` with `Copyright 2026 Matthew Gong`
* Reusable Flutter About and dependency-license control
* Widget coverage for registry navigation, content, and UI reachability

## Modified

* Credential updates now distinguish omitted, replacement, and explicit clear
* Provider configuration no longer exposes masks or activates before save
* Backup restore validates manifests, bounds archives, stages extraction,
  remaps provenance, and cleans up failures
* Starter actions, responsive panel behavior, accessibility, startup recovery,
  and Python version enforcement are operational
* API schemas and Flutter forms enforce matching input constraints
* Desktop artifacts include backend runtime files and verify completeness
* Root, frontend, and API documentation match current behavior
* Desktop artifacts include and verify the root license and attribution notice
* The README identifies Apache-2.0 and links both legal files
* Empty and populated application states expose the About control
* Desktop artifact verification requires compiled Flutter dependency notices
* The development script passes its backend URL to Flutter instead of allowing
  the app to launch a second backend
* Configured external backends are health-checked without being unloaded or
  terminated by Flutter
* Launcher regression coverage verifies URL normalization and process ownership
* User and contributor guidance describes script-owned and app-owned modes

## Deviations

* Packaged artifact layout was smoke-tested locally but not built on all hosted
  operating systems
* A remaining Starlette `TestClient` deprecation warning comes from upstream
  HTTPX migration guidance and does not affect runtime behavior

## Release Summary

Hypatia now has safer provider credentials and backups, functional first-run
actions, clearer startup recovery, responsive desktop panes, self-contained
application artifacts apart from documented external runtimes, and current
setup and API guidance. Source and desktop distributions now grant Apache-2.0
rights and retain the project attribution notice. Users can inspect compiled
dependency licenses from the app in every class state. Development startup now
runs one reload-enabled backend with explicit lifecycle ownership.