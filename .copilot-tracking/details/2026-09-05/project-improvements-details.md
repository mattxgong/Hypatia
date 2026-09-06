<!-- markdownlint-disable-file -->

## Context

* Plan: `.copilot-tracking/plans/2026-09-05/project-improvements-plan.instructions.md`
* Research: `.copilot-tracking/research/2026-09-05/project-improvements-research.md`
* Repository guidance: `CLAUDE.md`

## Phase Details

### Credential workflow

Use an explicit credential state instead of displaying server masks as input.
Omit unchanged secrets from updates, send an empty value only for an explicit
clear action, and delete empty values from the credential store.

### Backup restore

Parse and validate a typed manifest, inspect every ZipInfo before extraction,
stage the class directory, retain exported file IDs or map them consistently,
and commit database rows only after staged files are ready.

### Product usability

Use existing providers and callbacks for starter actions. Parse Python versions
before caching. Calculate side panel bounds from available width. Mirror server
validation in forms and remove test warnings.

### Distribution and integration

Bundle backend source and dependency metadata as Flutter assets or artifact
siblings, then teach the launcher to locate that packaged layout. Add a workflow
smoke check that verifies required backend files exist in each artifact.

### Documentation and final review

Update setup, configuration, frontend development, API contract, and licensing
material only after behavior stabilizes.

### Explicit licensing

Add canonical Apache-2.0 terms and project attribution at the repository root.
Copy and verify both legal files at the root of every desktop artifact.

### Dependency license access

Use Flutter's About dialog and registry-backed license page instead of building
a custom parser. Keep the entry point available in the empty state and class
sidebar. Verify compiled notices recursively because artifact paths differ by
desktop platform.

### Development backend ownership

Have `run_dev.sh` pass its Uvicorn URL through the compile-time
`HYPATIA_BACKEND_URL` definition. Normalize configured URLs in
`BackendLauncher`, health-check them without spawning a process, and skip model
unload and process termination when the launcher has no owned process. Keep the
empty-definition path unchanged so direct `flutter run` still provisions,
starts, and stops its own backend.
