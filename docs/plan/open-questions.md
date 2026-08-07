# Open Questions

Questions that need answers before or during implementation. Grouped by area.

---

## LLM Provider

1. **Which LLM providers should be supported at launch?**
   - **RESOLVED (2026-08-06):** All four: OpenAI, Anthropic (Claude), Ollama (local models), and GitHub Copilot. Default provider is **Claude (Anthropic)**.

2. **Should there be a default/recommended provider?**
   - **RESOLVED (2026-08-06):** Yes. **Claude (Anthropic)** is the default provider.

3. **What model should be used for wiki generation vs. chat queries?**
   - *Open.* Should heavier models be used for ingestion and lighter models for /ask? Should this be user-configurable per operation? Defer to implementation phase — make it configurable and test with Claude defaults.

---

## Architecture

4. **Should the backend run as a local server only, or also support remote deployment?**
   - *Open.* Start local-only. Remote deployment is a future consideration.

5. **How should the Flutter app launch the FastAPI backend?**
   - **RESOLVED (2026-08-06):** **Option B — Flutter app spawns the backend process automatically on launch.** The app will start the FastAPI/uvicorn process as a child process and manage its lifecycle (start on app launch, kill on app close).

6. **SQLite vs. PostgreSQL?**
   - *Open.* Start with SQLite. Design ORM layer so it's swappable. PostgreSQL only needed if going multi-user/remote.

---

## Video Processing

7. **Which Whisper implementation should be used?**
   - **RESOLVED (2026-08-06):** **`faster-whisper`** (CTranslate2 backend, ~4x faster on CPU). Not `speech_recognition` or `openai-whisper`.

8. **What Whisper model size should be the default?**
   - *Open.* Recommendation: Default to `base`, let user configure. Decide during Phase 2 implementation based on testing.

9. **Should GPU acceleration be supported for Whisper?**
   - *Open.* CPU by default, GPU as optional advanced config. `faster-whisper` supports CUDA natively.

---

## Frontend

10. **Which Flutter state management approach?**
    - *Open.* Plan recommends Riverpod. Confirm during Phase 5 implementation.

11. **Desktop-only or also mobile?**
    - **RESOLVED (2026-08-06):** **Desktop-first.** Mobile layout is a future phase (Phase 9+). The 3-panel layout targets desktop (Windows, macOS, Linux).

12. **Should the app support multiple windows/tabs for the same Class?**
    - *Open.* Recommendation: Single-window for now.

---

## Data & Storage

13. **Where should the data directory live?**
    - **RESOLVED (2026-08-06):** Default to **`~/.hypatia/data/`**, configurable in settings.

14. **Should there be a file size limit for uploads?**
    - **RESOLVED (2026-08-06):** **3GB initial limit**, subject to change in future phases.

15. **Should the app support importing existing markdown files directly into the wiki (not as raw sources)?**
    - *Open.* Defer to a future phase.

---

## Wiki Engine

16. **How should the LLM handle conflicts between sources?**
    - *Open.* The LLM Wiki pattern suggests flagging contradictions. Implement this — the LLM should note contradictions in wiki pages rather than silently picking one.

17. **Should wiki pages be editable by the user, or LLM-only?**
    - **RESOLVED (2026-08-06):** **Allow user edits, tracked separately.** User edits are preserved and won't be overwritten by LLM on rebuild. Implementation: store user edits in a separate layer or mark edited sections so the LLM can merge around them.

18. **How granular should citations be?**
    - *Open.* Start with page-level (PDF) and per-segment ~30s (video). Refine granularity in later phases.

---

## Scope

19. **Are there any additional chat commands beyond /ask, /summarize, and /remove?**
    - **RESOLVED (2026-08-06):** Yes. The full initial command set is:
      - `/ask "<query>"` — query the wiki
      - `/summarize <topic>` — generate a synthesis page
      - `/remove <file-path>` — remove a file and clean up references
      - `/lint` — wiki health check (find contradictions, orphans, broken links, stale pages)
      - `/rebuild` — regenerate the entire wiki from scratch
      - `/export` — export the wiki (format TBD: zip of markdown, PDF, etc.)
    - More commands may be added in future phases.

20. **Should there be a "Rebuild" button for the wiki, as shown in the MindBase UI?**
    - **RESOLVED (2026-08-06):** Yes. Both a UI button and the `/rebuild` command. This re-ingests all sources and regenerates all wiki pages (preserving user edits).

---

*Resolved questions are marked with date. Remaining open questions will be resolved incrementally during implementation.*
