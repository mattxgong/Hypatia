<!-- markdownlint-disable-file -->

## User Requests

* Implement the project-review recommendations in the recommended order
* Continue with follow-up option 3: add an explicit project license
* Use Apache-2.0 with `Copyright 2026 Matthew Gong`
* Continue with follow-up option 2: expose dependency licenses in the app
* Continue with follow-up option 2: unify development startup ownership

## Objectives

* Prevent credential corruption and make credential clearing durable
* Make backup restore bounded, atomic, and provenance-preserving
* Complete first-run actions and improve startup and responsive behavior
* Add server-side validation and focused workflow coverage
* Produce self-contained desktop release artifacts
* Align user and contributor documentation with implemented behavior
* Grant Apache-2.0 rights and include required legal files in distributions
* Keep compiled third-party notices reachable and verifiable in desktop builds
* Prevent `run_dev.sh` and Flutter from launching competing backend processes

## Context Summary

Follow `CLAUDE.md` and the applicable HVE Core Markdown and writing-style
instructions. Preserve all pre-existing uncommitted work.

## Implementation Checklist

### Phase 1: Credential workflow

<!-- parallelizable: false -->

* [x] Stop loading masked secrets into editable fields
* [x] Preserve unchanged credentials and explicitly delete cleared secrets
* [x] Make provider selection commit only after successful configuration
* [x] Add focused backend and frontend tests

### Phase 2: Backup restore

<!-- parallelizable: false -->

* [x] Validate versioned manifests before creating persistent state
* [x] Enforce archive entry and expanded-size limits
* [x] Stage extraction and clean up failures
* [x] Remap source file IDs during restore
* [x] Add traversal, limit, rollback, and provenance tests

### Phase 3: Product usability

<!-- parallelizable: true -->

* [x] Wire starter cards to usable actions
* [x] Enforce Python 3.11 or newer and add startup recovery actions
* [x] Protect the wiki center pane with responsive panel constraints
* [x] Add API and form validation
* [x] Correct WebSocket AsyncMock warnings

### Phase 4: Distribution and integration

<!-- parallelizable: false -->

* [x] Package backend sources and requirements with desktop artifacts
* [x] Make launcher resolve packaged backend resources
* [x] Add clean-artifact smoke validation where practical
* [x] Expand integration coverage for critical workflows

### Phase 5: Documentation and final review

<!-- parallelizable: true -->

* [x] Correct Ollama and Windows setup guidance
* [x] Replace Flutter boilerplate documentation
* [x] Document settings endpoints and distribution behavior
* [x] Resolve the missing license reference
* [x] Run all documented quality gates

### Phase 6: Explicit licensing follow-up

<!-- parallelizable: false -->

* [x] Confirm the license model and copyright holder
* [x] Add canonical Apache-2.0 terms and project attribution
* [x] Link the license and notice from the README
* [x] Include and verify legal files in desktop artifacts
* [x] Validate canonical text, workflow syntax, and packaging behavior

### Phase 7: Dependency license access

<!-- parallelizable: false -->

* [x] Add a reusable About and licenses control
* [x] Expose the control before and after a Class exists
* [x] Verify registry package names and license text are readable
* [x] Require nonempty compiled notices in every release artifact
* [x] Build and inspect a Windows release artifact

### Phase 8: Development backend ownership

<!-- parallelizable: false -->

* [x] Pass the script-owned backend URL to Flutter at compile time
* [x] Treat configured external backends as connect-only processes
* [x] Preserve application-owned startup for direct `flutter run`
* [x] Verify external shutdown does not unload or terminate the backend
* [x] Document and validate the single-owner development workflow

## Dependencies

* Existing FastAPI, SQLAlchemy, Flutter, Riverpod, and GitHub Actions tooling
* Existing backend virtual environment and Flutter SDK

## Success Criteria

* Focused tests pass after every phase
* Full backend and frontend quality gates pass
* No existing user changes are reverted
* Release artifacts include everything the launcher needs to start the backend
* Source and desktop distributions include Apache-2.0 terms and attribution
* Users can inspect compiled dependency licenses from every application state
* Development startup creates one backend process with one clear owner
