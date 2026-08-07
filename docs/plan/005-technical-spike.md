# Phase 0.5: Technical Spike

**Goal**: Validate the three highest-risk technical integrations before committing to the full implementation plan. Each spike produces a minimal proof-of-concept and a go/no-go decision.

**Prerequisites**: None (this is the very first phase).

**Outputs**: Working prototypes for faster-whisper transcription, LLM structured output parsing, and Flutter-to-Python subprocess management. Documented findings and any design adjustments needed.

**Duration**: 2-3 days.

---

## Tasks

### 0.5.1 Validate faster-whisper integration
Build a standalone Python script that:
- Installs `faster-whisper` and loads the `base` model.
- Transcribes a 5-minute sample video (extract audio with ffmpeg first).
- Produces timestamped markdown output.
- Measures: transcription speed (real-time factor), memory usage, output quality.
- Tests on CPU. If CUDA is available, test GPU path too.
- Documents any platform-specific issues (Windows DLL loading, macOS ARM compatibility).

**Go/No-go criteria**: Transcription completes in < 2x real-time on CPU with acceptable quality. If not, evaluate alternatives (cloud Whisper API, whisper.cpp bindings).

---

### 0.5.2 Validate LLM structured output parsing
Build a standalone Python script that:
- Sends a sample source document (2-3 pages of markdown) to the LLM with the wiki generation prompt.
- Instructs the LLM to produce multiple wiki pages in the XML-tagged format:
  ```
  <wiki-page path="pages/concepts/example.md">
  ---
  title: "Example Concept"
  ...
  ---
  Content here...
  </wiki-page>
  ```
- Parses the LLM output into discrete page objects.
- Tests with at least 2 providers (Claude and one other).
- Measures: parse success rate over 10 runs, failure modes, token usage.
- Documents prompt refinements needed for reliable structured output.

**Go/No-go criteria**: Parse success rate > 90% across 10 runs. If XML parsing is unreliable, evaluate alternatives (JSON mode, tool/function calling, multiple sequential calls).

---

### 0.5.3 Validate Flutter subprocess management
Build a minimal Flutter desktop app that:
- Spawns a Python HTTP server (simple `uvicorn` or `http.server`) as a child process.
- Detects when the subprocess is ready (polls a health endpoint).
- Displays status in the UI (starting → ready → error).
- Gracefully kills the subprocess on app close.
- Tests on **Windows** (primary) — verify:
  - Python discovery (PATH, common install locations, `py` launcher).
  - Process tree cleanup (killing parent kills children on Windows).
  - Port conflict detection and recovery.
- Tests on macOS/Linux if available.
- Documents: how to find Python, what happens if Python isn't installed, how to handle `venv` activation.

**Go/No-go criteria**: Subprocess reliably starts and stops on Windows. Health check polling works. No orphan processes after app close.

---

## Sequencing

All three spikes are independent and can run in parallel:

```
0.5.1 (faster-whisper) ─┐
0.5.2 (LLM parsing)    ─┼──→ Document findings ──→ Adjust Phase 1-3 plan if needed
0.5.3 (Flutter subprocess)┘
```

---

## Decision Points

After the spikes, review findings and adjust the plan:

| Spike | If it fails | Plan adjustment |
|-------|-------------|-----------------|
| faster-whisper | Falls back to cloud Whisper API or whisper.cpp | Update Phase 2, add network dependency for transcription |
| LLM parsing | Switch to JSON mode or sequential calls | Update Phase 3, change output format and parsing strategy |
| Flutter subprocess | Ship backend separately, user starts manually | Remove Task 1.9 auto-launch, add setup instructions instead |

---

## Outputs

Each spike produces:
1. A working script/app in `spikes/` directory (not shipped, just for validation).
2. A brief findings document noting: what worked, what didn't, platform issues, performance numbers.
3. Any adjustments needed to subsequent phases (fed back into the plan).
