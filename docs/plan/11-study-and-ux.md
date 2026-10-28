# Phase 11 (proposed): Study Feedback, Chat, and Visual Polish

**Goal**: Make studying and chatting feel guided instead of one-shot. A finished quiz leads
into a tutoring conversation about the mistakes, chat suggests where to go next, wiki pages
and sources can be referenced directly from the input box, and long operations explain what
they're doing. Alongside that, put the theme and pane layout on a consistent footing before
the mobile layouts are built on top of them.

**Prerequisites**: Phase 9 complete. Parts of this phase are scheduled before, inside, and
after Phase 10 (see "Ordering relative to Phase 10").

**Outputs**: Mistake review from quiz results, a session summary screen, suggested follow-up
replies in chat, `@` references in the chat input, grouped progress for long operations, a
semantic theme extension and pane-layout rules, and an LLM-judged evaluation suite for answer
and study-material quality. Larger items (study modes, a per-page proficiency estimate, paged
retrieval tools, concept maps, per-task model selection, crash-safe jobs) are listed as
options for later.

**Status**: Planning only, not started. Drafted 2026-10-28.

---

## Ordering relative to Phase 10

Phase 10 (mobile) hasn't started. This phase is split into three waves so that nothing
Phase 10 builds on has to be redone:

| Wave | When | Tasks | Why this timing |
|---|---|---|---|
| **A** | Before Phase 10 | 11.1, 11.2, 11.3, 11.4, 11.5 | 11.1-11.3 settle the study data that Phase 10's offline cache (10.14) snapshots. 11.4-11.5 restyle and restructure `home_screen.dart` once, before 10.12 splits it into compact, medium and expanded layouts. |
| **B** | Inside Phase 10 | 11.6, 11.7, 11.8 | Folded into the Phase 10 task that touches the same code: chat input and suggestion chips with 10.12b's chat adaptation (W14), and crash-safe jobs with the tray lifetime in 10.1 (W9). |
| **C** | After Phase 10, or in any gap | 11.9, 11.10, 11.11-11.16 | Independent of mobile. 11.10 (evals) is backend-only and can be pulled earlier to guard prompts while Phase 10 is in progress. |

Wave A is small (about 1.5-2 weeks solo). It shouldn't delay Phase 10's M0 by more than that.

---

## Current state (verified 2026-10-28)

Several pieces this phase builds on already exist. Don't rebuild them:

- `quiz_prompt.py` already asks for an `<explanation>` per question and a `<rubric>` per
  short-answer question. `llm_generator.py` stores the rubric in `answer_json` and drops
  MCQs without exactly one correct choice.
- `grading_prompt.py` returns `<score>` (0-1) and `<feedback>`. `service.py` stores
  per-question results in `quiz_attempts.grading_json`.
- `flashcard_review.dart` already handles Space to reveal and 1-4 to rate. `quiz_view.dart`
  has no keyboard handling.
- `theme.dart` derives a `ColorScheme` from seed `0xFF7C4DFF`, overrides the dark surface
  ramp, and has one `ThemeExtension` (`StatusColors`). Corner radii are literals (for
  example `BorderRadius.circular(8)`).
- `home_screen.dart` already persists pane widths and collapsed panes, with 12px resize
  handles (commit 8e63491).
- Polling: `task_provider.dart` and `file_provider.dart` every 3 s, `study_provider.dart`
  every 2 s. `task_manager.py` keeps tasks in memory only.

---

## Wave A: before Phase 10

### 11.1 Review mistakes from quiz results

After a submitted attempt, a **Review my mistakes** button on the results view opens chat
with a tutoring session about the questions the user got wrong or partly wrong.

**Implementation details:**
- New chat command `/review-quiz <attempt_id>` (also triggered by the button). The router
  builds the context from the attempt. For each incorrect or partial question it includes the
  prompt, the user's answer, the correct or reference answer, the stored explanation and the
  grader's feedback, plus the cited wiki pages within the `_prompt_budget`.
- System prompt rule: work only on the listed mistakes, starting with the most fundamental.
  Don't re-explain questions the user got right. Ask one check question per mistake before
  moving on.
- **Don't spoil quizzes in progress.** If an attempt for a quiz is started but not submitted,
  `/ask` must not include that quiz's answers in its context. This is a test case, not new
  logic: the current `/ask` doesn't read quizzes. Keep it that way.
- The command runs in the per-connection worker like other commands and saves to chat history.

**Acceptance**: Unit test that the context contains only incorrect or partial questions.
E2E test: submit a quiz with one wrong answer, run the command with a mock LLM, and see a
reply saved to history.

### 11.2 Weighted questions and partial credit display

**Implementation details:**
- Add `points` (int, default 1) to `quiz_questions` with an Alembic migration, and include it
  in backups. The LLM prompt may assign 1-3 points by difficulty. Heuristic questions stay at 1.
- Attempt score becomes the sum of `score x points` over the sum of points. Short answers keep
  the 0-1 score from grading.
- `quiz_view.dart` shows per-question points and partial credit (for example "1.5 / 3").
- Extend the existing generation validation to matching and true/false: drop a matching
  question whose pairs aren't one-to-one, and a true/false whose answer isn't a boolean.

**Acceptance**: Migration up/down test. Scoring unit tests with mixed weights. Validation
tests for malformed matching and true/false output.

### 11.3 Session summary screen

When a flashcard review session or quiz ends, replace the bare "done" state with a summary:
cards reviewed per rating, quiz score, the wiki pages with the most misses (links), and when
the next cards are due.

**Implementation details:**
- Computed client-side from the session's ratings plus the deck's `due_count`
  (`GET /decks/{deck_id}`). "Next due" needs the earliest future `due_at`; add it to
  `DeckRead` if it isn't cheap to derive client-side. No new table.
- "Weak pages" = pages referenced by cards rated `again` or by questions scored below 0.5.
- Respect reduced motion (no celebration animation when `MediaQuery.disableAnimations`).

**Acceptance**: Widget tests for an all-correct session, an all-`again` session, and a quiz
with no page references.

### 11.4 Semantic theme tokens

Replace ad-hoc colors and radii with one theme extension so every later layout (including
Phase 10's) reads the same slots.

**Implementation details:**
- Extend `StatusColors` (or replace it with a broader `HypatiaTokens` extension):
  - Text levels: primary, secondary, muted.
  - Lines: hairline and strong border.
  - Accent tint: the seed color at low opacity, for selected rows and pills.
  - Status: success, warning, danger.
  - Elevation: three shadow levels.
- One base radius (10) with derived small, large and pill sizes. Replace `BorderRadius.circular`
  literals across `widgets/`.
- Keep the violet seed as the only strong color. Everything else is neutral.
- Frosted backgrounds (`BackdropFilter`) only on floating elements, such as the chat input
  over scrolling content. Not on panels.
- Optional: a bundled variable font with wide script coverage, so non-Latin wiki content
  doesn't fall back to mixed system fonts. Decide before 10.12, since font metrics affect
  compact layouts.

**Acceptance**: `flutter analyze` clean, golden or widget tests for light and dark themes,
and no `Color(0x...)` literals left in `widgets/` outside the theme (a grep in CI or a test).

### 11.5 Pane layout rules

Tidy the three-panel layout in `home_screen.dart` before 10.12 (W13) generalises it.

**Implementation details:**
- Dividers only resize. Double-clicking a divider resets that pane to its default width.
- Collapse and expand buttons live in each pane's header, not on the divider.
- Pane widths and collapsed state already persist (commit 8e63491). Check that they're
  clamped to the current window size on load, which matters once 10.12 makes windows resizable
  between size classes.
- The collapsed sidebar becomes a narrow strip of icons (Wiki, Sources, Study, Search).
  Clicking an icon expands the sidebar on that section.
- Keep the chat panel mounted when the wiki page, source or study view changes, so an unsent
  draft and the scroll position survive. Move the draft into a Riverpod provider (10.12 needs
  this anyway for rotation and resize).
- Keyboard for `quiz_view.dart`, following the rules in `flashcard_review.dart`: ←/→ between
  questions, 1-9 to pick a choice. Ignore keys while a text field has focus or a modifier is held.

**Acceptance**: Widget tests for resize, double-click reset, collapse persistence, and the
draft surviving a page switch. Quiz keyboard test with a focused short-answer field (keys
must type, not navigate).

---

## Wave B: inside Phase 10

### 11.6 Suggested follow-up replies

After an `/ask` answer, show 2-4 short tappable follow-ups, for example "Give an example",
"Quiz me on this", or a question about a related page.

**Implementation details:**
- The query prompt asks for an optional `<suggestions>` block after the answer (each item at
  most about 60 characters). The parser strips the block from the streamed answer text.
- Normalise rather than reject: trim, drop duplicates and empties, cap at 4, and drop the
  block entirely if it's malformed. Never fail the answer over it.
- Sent as a `suggestions` list on the WebSocket `complete` frame and stored in the message's
  `metadata_json`, so they show again after a reconnect. Update `api-contract.yaml`.
- Chips sit under the latest assistant message only. Tapping one sends it as the next message.
- Schedule with 10.12b (W14) chat adaptation: the chips are the main way to continue a
  conversation on a phone without typing.

**Acceptance**: Parser tests with valid, missing, oversized and malformed blocks. Widget
test that chips appear only on the latest message.

### 11.7 `@` references in the chat input

Typing `@` in `command_input.dart` opens a picker over the Class's wiki pages and sources.
The chosen item becomes a pill in the input and is sent as a typed reference, not pasted text.

**Implementation details:**
- Picker uses the existing search endpoint (pages) and the file list (sources), filtered as
  the user types. Keyboard: arrows and Enter. Touch: tap.
- The message frame gains `refs: [{kind: "page"|"source", id}]`. The backend puts referenced
  items first in the context, ahead of search results, within the prompt budget. Sources use
  their converted markdown.
- Sources that aren't `READY` show their status in the picker and can't be attached.
- Pills are removed with Backspace or their close button. Stored in `metadata_json` so
  history shows what was referenced.
- Schedule with W14, so the picker is designed once for keyboard and touch.

**Acceptance**: Backend test that referenced pages are in the context even when search would
not rank them. Widget tests for the picker, pill removal and the not-ready state.

### 11.8 Crash-safe background jobs

Persist ingest and study-generation jobs so they resume after a backend crash or restart,
instead of living only in `task_manager.py`'s memory.

**Implementation details:**
- A `jobs` table: kind, class, state, progress, a JSON checkpoint (for ingest: chunks done
  and the in-memory page set so far, or just "restart from the beginning" if that's simpler),
  `heartbeat_at`, and an `attempt` counter.
- The worker updates the heartbeat while running. On startup, jobs whose heartbeat is stale
  are re-queued. Every write checks the `attempt` it started with, so a stale worker can't
  overwrite a newer run.
- Ingest's "write everything in one transaction at the end" rule stays. A resumed job either
  finishes and commits, or changes nothing.
- `task_manager` keeps serving the polling API, reading from the table.
- Schedule with W9 (tray lifetime): a backend that stays up for days makes interrupted jobs
  more likely and more annoying.

**Acceptance**: E2E test that kills the worker mid-ingest (simulated), restarts, and gets the
same wiki as an uninterrupted run. Test that a stale worker's write is rejected.

---

## Wave C: after Phase 10

### 11.9 Grouped progress for long operations

Show ingest, `/rebuild` and `/lint` as one collapsible group in chat, with one plain sentence
per step ("Read lecture-3.pdf", "Updated 4 pages", "Committed to history"). The group
collapses a few seconds after finishing, and raw details sit behind an expander. When the
provider returns reasoning text, show a one-line preview of it above the group, collapsed by
default. Builds on the existing `progress` frames and `activity_status.dart`. Each progress
step type needs a human-readable label; a test fails if one is missing.

### 11.10 Answer and study-material evals

A `backend/evals/` suite run nightly (`nightly.yml`), not in the fast CI run.

- Fixtures: two or three small Classes with known sources, plus question sets.
- Judged checks, each a yes/no from a judge model:
  - `/ask`: does the first sentence answer the question, and does every factual claim carry
    a citation?
  - Flashcards: is the card answerable from its cited page?
  - Quiz: is exactly one choice defensible?
- Parse the judge's verdict strictly. A malformed verdict counts as "unjudged" and is
  reported, never counted as a pass or fail.
- Output a markdown report per run with pass rates per check, saved as a CI artifact.

Can be pulled into Phase 10's timeline, since it touches nothing Phase 10 changes.

### Later options (decide individually)

| ID | Option | Notes |
|---|---|---|
| 11.11 | **Study modes** | Editable markdown "mode" files per Class. *Teach-back*: the user explains a page, and the LLM finds the 1-2 biggest gaps and asks guiding questions instead of answering. *Spiral review*: older topics resurface in chat. *Fact-check*: an answer is checked against the cited sources. Invoked as `/teach <page>` and similar. |
| 11.12 | **Proficiency per page** | The LLM only labels events (confused, asked for a hint, self-corrected). Plain Python combines those labels with quiz and review results into a smoothed score per page, with a minimum number of signals and hysteresis so one answer doesn't flip it. Drives quiz difficulty and `/ask` depth. Complements SM-2 rather than replacing it. |
| 11.13 | **Paged retrieval tools for chat** | Let `/ask` read a page or source in chunks (with a revision so it notices edits), search the Class, and list sources. Read-only, with no remove or delete. Keep the system prompt fixed so provider prompt caching keeps working. Locate chunks by page and heading for finer citations. Needs tool-calling support in all four providers. |
| 11.14 | **Concept map** | A graph of a Class's wiki pages and their links, drawn natively in Flutter, opening pages on tap. |
| 11.15 | **Model per task** | Choose a model for ingest, chat, study generation and grading, each falling back to the default. One settings card per task in `class_settings_screen.dart` / the provider dialog. |
| 11.16 | **Change-based refresh** | A revision counter per Class, bumped on every committed change. Providers fetch only when it moves, instead of polling everything every 2-3 s. Pairs well with mobile data use. |

**Out of scope**: multi-character classroom discussions, whiteboard drawing, voice narration,
slide generation, PowerPoint export/import, and running generated HTML. They're expensive and
don't serve a personal, wiki-first study app.

---

## Open questions

1. 11.2: should the LLM assign points, or should the user set a per-quiz difficulty that
   maps to points?
2. 11.4: bundle a font, or keep the platform default?
3. 11.8: is a full ingest restart on resume acceptable (simpler), or is chunk-level
   checkpointing worth the complexity?
4. 11.10: which model judges? It should differ from the model under test where possible.
