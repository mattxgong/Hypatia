<!-- markdownlint-disable-file -->

## Discrepancy Log

* The worktree contains ongoing native Ollama changes. Implementations must
  integrate with them instead of restoring the committed baseline.
* Final backend validation exposed Windows path separators in exported backup
  manifests. Export now emits POSIX paths, while restore safely normalizes
  legacy separators before traversal checks.
* Phase 3 review found cached Python executable paths were split on spaces.
  Existing executable paths are now preserved as one command token.
* The manual workflow was validated through YAML diagnostics and local
  artifact assembly. Hosted Windows, macOS, and Linux builds were not invoked.
* The initial review could not responsibly choose a license and removed the
  broken reference. The user later selected Apache-2.0 with Matthew Gong as
  the 2026 copyright holder.

## Implementation Paths

* Selected incremental, test-first changes grouped by user-visible workflow
* Rejected a broad rewrite because current quality gates are green and the
  defects are concentrated in specific state transitions
* Selected the canonical Apache-2.0 license plus a project `NOTICE`; desktop
  archives copy and verify both files at their artifact root
* Selected Flutter's native About dialog and `LicenseRegistry` so dependency
  attribution comes from the same compiled data as packaged applications
* The focused test required two corrections to match Flutter behavior: the
  localized action is `View licenses`, and package entries expand before their
  license body is rendered
* Release validation now searches recursively for a nonempty `NOTICES` or
  `NOTICES.Z`, which supports Windows, Linux, and nested macOS bundles
* Selected a compile-time `HYPATIA_BACKEND_URL` handoff because `run_dev.sh`
  already owns the reload-enabled process and Flutter only needs its address
* Removed the redundant `devMode` flag: a nonempty external URL now defines
  connect-only behavior, while an absent URL preserves automatic ownership
* Moved Ollama unload behind the owned-process check so closing Flutter cannot
  mutate or stop a script-owned backend
* A loopback HTTP test verifies external startup performs one health request
  and external shutdown performs no unload request
* The WSL `bash` shim lacked a distribution, so script syntax validation used
  Git for Windows Bash and passed

## Suggested Follow-on Work

* Evaluate cloud or multi-user authentication only if the deployment model
  expands beyond a loopback desktop companion
* Run the manual release workflow on hosted Windows, macOS, and Linux runners
  and inspect its downloadable archives
* Synchronize the About dialog version with Flutter build metadata
* Replace the deprecated Starlette `TestClient` HTTPX integration when the
  ecosystem migration path is available
