# Phase 9: Study Tools (Flashcards & Practice Tests)

**Goal**: Let users turn a Class's wiki into flashcard decks (with spaced-repetition review) and practice tests (with grading and explanations), using either offline heuristics or an LLM.

**Prerequisites**: Phases 3B, 4, 6, and 7 complete (wiki engine, REST/WebSocket API, frontend shell, hybrid search).

**Outputs**: A `study` backend module (models, generators, scheduler, router), chat commands `/flashcards` and `/quiz`, a Study section in the frontend with review and test-taking views, and Anki/CSV export.

**Status**: Implemented 2026-10-01: wave 1 (offline MVP: 9.1-9.4, 9.6 heuristic-only, 9.8, 9.9), wave 2 (9.5 AI generation and grading, 9.7 chat commands), and 9.10 (docs and E2E). Native `.apkg` export remains a stretch item. Open questions resolved 2026-10-01 (see Decisions Log).

---

## Feasibility Summary

The wiki is a good input for study material because ingestion has already done the hard work: every
concept/entity page is a curated, cited, single-topic article with a title, tags, and
`hypatia://cite` links. Most generation can work from wiki pages rather than raw sources, which
keeps prompts small and gives every card/question a citation back to the wiki and source.

| Approach | Flashcards | Practice test | Quality | Cost / offline |
|---|---|---|---|---|
| Heuristic (no AI) | Good for definitions, term/term-pairs, cloze | MCQ/T-F/matching/fill-in from cards; distractors from sibling cards | Medium; depends on wiki structure | Free, offline, deterministic |
| Local embeddings (optional `semantic` extra) | Dedup near-duplicate cards | Better distractors (nearest-neighbour definitions) | Improves heuristic quality | Free, offline |
| LLM | Conceptual Q/A, "why/how" cards, worked examples | MCQ with plausible distractors, short answer, explanations | High | Token cost; needs provider |
| LLM grading | n/a | Free-response grading against a rubric | High, non-deterministic | Token cost |

Recommendation: ship heuristic generation first (always available, testable with golden files),
then LLM generation behind the same interface, then a hybrid mode where heuristics propose
candidates and the LLM rewrites/filters them and supplies distractors.

---

## Option Analysis

### Non-AI techniques

All of these operate on wiki page markdown after `stripFrontmatter`-equivalent parsing on the backend.

1. **Page-as-card**: concept/entity page title -> front; first non-heading paragraph (trimmed to N sentences, citations preserved) -> back. Highest-yield heuristic because each page already covers one idea.
2. **Definition patterns**: regex over sentences/list items for `**Term** - definition`, `**Term**: definition`, `Term is/are/refers to/means ...`, markdown definition-like lists, and the first sentence under a heading.
3. **Two-column tables**: each row becomes a card (left cell front, right cell back) when the header looks like term/definition, symbol/meaning, date/event, etc.
4. **Cloze deletions**: in sentences that contain a known key term (bold text, `[[wiki link]]` targets, page titles, tags), blank the term -> `The {{c1::mitochondria}} produces ATP`. Keep only sentences with exactly one strong term and a length cap.
5. **Key-term ranking**: simple TF-IDF across the Class's pages (pure Python, no new dependency) to rank which terms deserve cards when the user asks for a fixed count.
6. **Question assembly** for tests, from the card pool:
   - Multiple choice: correct back + 3 distractor backs from cards sharing a tag/category (or nearest embedding neighbours when `sentence-transformers` is installed).
   - True/false: pair a front with its own back or a distractor back.
   - Matching: 4-6 front/back pairs shuffled.
   - Fill-in-the-blank: cloze cards, graded by normalized string match (case/whitespace/punctuation-insensitive, optional accepted aliases).
7. **Spaced repetition**: in-house SM-2 (about 40 lines, no dependency). The `fsrs` package was considered and not adopted.
8. **Export**: Anki and Quizlet both import TSV, so CSV/TSV export needs no dependency and is the baseline. Native `.apkg` export via `genanki` (MIT) is preferred but not required; it is a stretch item behind an optional `anki` extra.

Rejected for v1: local transformer question-generation models (for example T5-based QG). They add a large `transformers` dependency and model download, and quality is below a hosted LLM while still being "AI".

### AI techniques

1. **LLM flashcards**: prompt with the selected pages (budgeted like `wiki_engine` ingestion, `tiktoken` counting) and ask for cards in a tagged format consistent with `wiki_parser.py`, for example:

   ```xml
   <card type="basic" page="pages/concept/entropy.md">
   <front>What does the second law of thermodynamics say about entropy?</front>
   <back>Entropy of an isolated system never decreases. [source](hypatia://cite?file=lec3.pdf&page=4)</back>
   </card>
   ```

   `LLMProvider` only returns `str`, so a tolerant XML-tag parser (same approach as `parse_llm_output`) is used rather than relying on provider JSON modes.
2. **LLM practice tests**: same pattern with `<question type="mcq|tf|short">`, `<choice correct="true">`, `<answer>`, `<explanation>`, each required to cite a page or source.
3. **LLM grading** for short-answer questions: one call per answer with the reference answer and rubric, returning a score and feedback. On by default; the user can turn it off per quiz. When it is off or no LLM is available, the user self-grades by comparing to the reference answer.
4. **Validation** applied to all LLM output: drop items without a valid page/source reference, drop MCQs whose correct choice count is not exactly one, dedup by normalized front text (and embeddings if available), cap count.
5. **Small-context models** (Ollama defaults to 4096 tokens): generate per page instead of per batch; fall back to heuristic mode if the provider is unavailable.

### Hybrid mode

Heuristics produce candidate cards; the LLM receives them plus the source pages and is asked to rewrite unclear fronts, drop trivial cards, and add distractors. This cuts tokens compared to free generation and keeps output anchored to the wiki.

---

## Design Decisions

- **Database only.** Cards carry mutable review state and are not knowledge; storing them as wiki pages or committing them to the per-Class wiki git repo would pollute search, lint, rebuild, and git history. Study data lives only in new DB tables (and in backups).
- **Generation scope** is one of: whole Class, topic (via `hybrid_search`), explicit page list, or a source file (pages whose `source_file_ids` contain it).
- **Generation runs as a background task** through `task_manager`, reported with existing `progress` messages; it does not block chat.
- **Flag as out of date; never auto-regenerate.** When `/remove`, `/rebuild`, or a page edit changes a referenced page, affected cards/questions are flagged `stale` so review history is not lost. The user can regenerate or delete them.
- **AI grading on by default** for short-answer questions, with a per-quiz toggle and self-grading fallback.
- **Heuristic mode is always available**; AI and hybrid modes are disabled in the UI when `check_llm_available` fails.

---

## Tasks

### 9.1 Data model and migration

Add ORM models to `backend/app/models/db_models.py` and an Alembic migration.

**Implementation details:**
- `decks`: `id`, `class_id` (FK, cascade), `name`, `description`, `generation_method` (`heuristic` | `llm` | `hybrid`), `scope_json`, timestamps.
- `flashcards`: `id`, `deck_id` (FK, cascade), `card_type` (`basic` | `cloze` | `reverse`), `front`, `back`, `page_paths` (JSON), `source_file_ids` (JSON), `origin` (`heuristic` | `llm` | `user`), `stale` (bool), SM-2 state (`ease`, `interval_days`, `repetitions`, `lapses`, `due_at`, `last_reviewed_at`), timestamps.
- `quizzes`: `id`, `class_id`, `name`, `generation_method`, `scope_json`, `settings_json` (question count, types, time limit, `ai_grading` defaulting to `true`), timestamps.
- `quiz_questions`: `id`, `quiz_id`, `position`, `question_type` (`mcq` | `tf` | `matching` | `fill` | `short`), `prompt`, `choices_json`, `answer_json`, `explanation`, `page_paths`, `source_file_ids`, `stale`.
- `quiz_attempts`: `id`, `quiz_id`, `started_at`, `submitted_at`, `answers_json`, `score`, `max_score`, `grading_json` (per-question result/feedback).
- New str enums stored by `.value` using the existing `values_callable` helper.
- Extend `backend/app/routers/backup.py` manifest/serializers so backup round-trips include study data.

**Acceptance**: Migration upgrades/downgrades cleanly (`test_migrations.py`); deleting a Class cascades; backup export/import preserves decks, review state, quizzes, and attempts.

### 9.2 Heuristic extractors

New module `backend/app/services/study/extractors.py`.

**Implementation details:**
- Functions per technique: `cards_from_page_lead`, `cards_from_definitions`, `cards_from_tables`, `cloze_from_key_terms`, plus `rank_key_terms` (TF-IDF over the Class's pages).
- Shared `CardCandidate` dataclass (`front`, `back`, `card_type`, `page_path`, `source_file_ids`, `score`).
- Preserve inline `hypatia://cite` links in backs; strip `[[...]]` to display text.
- Skip `index`/`log` pages; dedup by normalized front.

**Acceptance**: Golden-file tests in `backend/tests/golden/` covering definitions, tables, cloze, math (`$...$` kept intact), and pages without usable structure (yield zero cards, no crash).

### 9.3 Heuristic test builder and grading

`backend/app/services/study/quiz_builder.py` and `grading.py`.

**Implementation details:**
- Build MCQ, T/F, matching, and fill-in questions from a card pool; distractors from same tag/category, then nearest embeddings when `embedding_service` is importable, then random.
- Seedable RNG so tests are deterministic.
- Deterministic grading for MCQ/T-F/matching/fill (normalized match with aliases).

**Acceptance**: Unit tests for distractor uniqueness (never equals the correct answer), seed determinism, and grading normalization.

### 9.4 Spaced-repetition scheduler

`backend/app/services/study/scheduler.py` implementing SM-2 in-house (no new dependency) with ratings `again | hard | good | easy`.

**Acceptance**: Table-driven tests for interval/ease progression and lapse handling; `due_at` uses UTC.

### 9.5 LLM generation and grading

`backend/app/services/prompts/flashcard_prompt.py`, `quiz_prompt.py`, `grading_prompt.py`, and `backend/app/services/study/llm_generator.py`.

**Implementation details:**
- Context budgeting reused from `wiki_engine` (schema + pages + output reserve), batching pages when over budget.
- Tolerant tag parser for `<card>` and `<question>` blocks; validation rules from the Option Analysis section.
- Hybrid mode: pass heuristic candidates in the prompt for rewrite/filter and distractor generation.
- Short-answer grading call returns `<score>` and `<feedback>`; runs by default when `settings_json.ai_grading` is true. If the LLM is unavailable or the call fails, the answer is marked `needs_self_review` instead of failing the attempt.
- Add the new module to `_LLM_PROVIDER_TARGETS` in `tests/e2e/conftest.py` because it imports `get_llm_provider`.

**Acceptance**: Mocked-LLM unit tests for parsing malformed output, dropping uncited items, batching, and grading fallback when the LLM is unavailable; prompt regression cases in `test_prompt_regression.py`; one `@pytest.mark.integration` test per prompt for the nightly run.

### 9.6 Study API

New router `backend/app/routers/study.py`, schemas in `schemas.py`, and `docs/api-contract.yaml` updates.

**Implementation details:**
- `POST /api/classes/{class_id}/decks/generate` and `POST /api/classes/{class_id}/quizzes/generate` -> `{task_id}`; body: `scope`, `method`, `count`, `card_types`/`question_types`.
- Deck CRUD, card CRUD (user can add/edit cards, `origin=user`), `GET /decks/{deck_id}/due?limit=`, `POST /flashcards/{card_id}/review` with rating.
- Quiz CRUD, `POST /quizzes/{quiz_id}/attempts` (submit answers -> graded result), `GET /quizzes/{quiz_id}/attempts`.
- `GET /decks/{deck_id}/export?format=csv|tsv` (Anki/Quizlet import compatible).
- Stretch: `format=apkg` via `genanki` in an optional `anki` extra (same pattern as `semantic`). Returns a structured `HypatiaError` when the package is missing; `GET /decks/{deck_id}/export/formats` lets the frontend hide the option. Regenerate `requirements.lock` after adding the extra.
- `PATCH` on a quiz/attempt to toggle `ai_grading` and to submit self-grades for `needs_self_review` answers.
- Errors through `HypatiaError` subclasses; add `ErrorCode` entries only where existing codes do not fit.
- Staleness hook: after `handle_remove`/`handle_rebuild`/page updates, mark cards/questions whose `page_paths` changed as `stale`.

**Acceptance**: Router tests in `test_study_router.py`; contract and schemas consistent.

### 9.7 Chat commands

Add `/flashcards [topic]` and `/quiz [topic]` to `command_parser.py`, `/help`, and `chat.py`.

**Implementation details:**
- Default method: LLM when available, otherwise heuristic (announced in the reply).
- Reply with a summary (`Created deck "Entropy" with 18 cards`) and metadata the frontend uses to open the deck/quiz.

**Acceptance**: `test_command_parser.py` and `test_chat_router.py` cases for both commands with and without topic, and with the LLM unavailable.

### 9.8 Frontend: study navigation and generation dialog

**Implementation details:**
- Sidebar "Study" section under the wiki tree listing decks (with due count) and quizzes.
- Center panel switch via a new `centerViewProvider` (`wiki | deck | quiz | quizResult`) in `home_screen.dart`, which today always shows `WikiViewer`.
- `study_provider.dart` (Riverpod) and `api_client.dart` methods for the new endpoints; generation progress via the existing task indicator.
- Generation dialog: scope (Class / topic / current page / source file), method (Heuristic / AI / Hybrid, AI disabled when unavailable), count, types, and an "AI grading" switch (on by default, disabled when no LLM is available).

**Acceptance**: Widget tests for the dialog states and sidebar listing.

### 9.9 Frontend: review and test-taking views

**Implementation details:**
- Flashcard review: flip card, keyboard shortcuts (space to flip, 1-4 to rate), progress bar; render front/back through the wiki markdown pipeline (`stripFrontmatter` -> `resolveWikiLinks` -> `numberCitations`, math via `markdown_math.dart`) so citations and LaTeX work.
- Card editor for user edits and a "stale" badge with regenerate/delete actions.
- Quiz runner: one question per screen or full list, submit, then result view with per-question correctness, explanation, AI feedback, and citation links that open the wiki page or source viewer. Answers marked `needs_self_review` show the reference answer with correct/incorrect buttons.
- Export action for decks (save CSV/TSV via `file_picker`; `.apkg` shown only when the backend reports it as available).

**Acceptance**: Widget tests for flip/rate flow and quiz submission; manual check on Windows/macOS/Linux.

### 9.10 Documentation and E2E

- Update `CLAUDE.md` (structure, tables), `README.md` features, `docs/troubleshooting.md` (empty deck when wiki has no concept pages).
- E2E scenario: ingest fixture -> heuristic deck -> review -> quiz attempt -> backup/import round-trip.

**Acceptance**: E2E test passes in CI with mocked LLM.

---

## Suggested Order

```text
9.1 -> 9.2 -> 9.3 -> 9.4 -> 9.6 (heuristic-only API) -> 9.8 -> 9.9   (usable offline MVP)
                         \-> 9.5 -> 9.7                                (AI + chat commands)
                                              all -> 9.10
```

---

## Wave 1 Implementation Notes

Differences from the task text above, for wave 2 to build on:

* **Staleness is computed, not stored.** Cards and questions keep `page_hashes` (`{page_path: hash of the page body}`) instead of a `stale` column. Any mismatch with the current page body marks them out of date, so every mutation path (ingest, `/remove`, `/rebuild`, user edits) is covered without hooks in `wiki_engine`. Frontmatter-only changes do not count.
* **Heuristic generation is synchronous.** `POST .../decks/generate` and `.../quizzes/generate` return the created deck or quiz directly (201). LLM generation in wave 2 should move to a `task_manager` background task.
* **Refresh instead of per-card regenerate.** `POST .../decks/{id}/refresh` re-extracts out-of-date generated cards: a card whose front still appears keeps its review history and gets the new back; one that no longer appears is removed. User cards are only flagged; `PATCH` with `acknowledge_changes` accepts the current pages.
* **Export formats** are `csv` (generic, Quizlet) and `anki` (TSV with Anki file headers and Basic/Cloze note types). Native `.apkg` remains a stretch item.
* **Distractors** use tag overlap, vocabulary overlap, and length similarity; embeddings are not used yet. Each choice hides its own subject term (including wiki links and a following abbreviation) so options do not give away answers.
* **Short-answer** questions are rejected for heuristic quizzes; `ai_grading` (default `true`) is stored in `settings_json` for wave 2.

## Wave 2 Implementation Notes

* **Background jobs.** `method: llm|hybrid` on either generate endpoint checks the scope and LLM up front (422 / 503), then returns 202 `{task_id, kind}` and runs in `services/study/jobs.py`. The task's new `result` field (`kind`, `id`, `name`, `count`) identifies what was made. Cancelling stops between batches and saves nothing.
* **Batching.** Pages are packed into batches sized from the model's context window (same budget helpers as the wiki engine), so small Ollama models get one or two pages per call. A failed batch is skipped; the job fails only if every batch fails.
* **Output validation.** Cards and questions must name a page from their batch (path, slug, or title); MCQ needs exactly one correct of 3-6 distinct choices; matching needs 3-6 pairs; fill needs a blank. Results are deduplicated and interleaved across pages (cards) or question types (quizzes).
* **Hybrid.** Decks send offline cards as drafts to rewrite or drop; quizzes send offline basic cards as key facts. Drafts get up to a quarter of the prompt budget.
* **AI grading.** Typed short answers are graded concurrently on submit (`score >= 0.7` counts as correct, partial credit kept). If grading is off or the LLM fails, the answer is `needs_self_review`; `PATCH .../attempts/{id}` records the user's verdict. Results carry `feedback` and `grader` (`ai`/`self`).
* **Refresh** only re-extracts heuristic cards; AI and user cards stay flagged until edited, kept, or deleted.
* **Chat.** `/flashcards [topic]` and `/quiz [topic]` use AI when `check_llm_available` passes (progress is relayed as `progress` messages), otherwise build offline and say so. The frontend opens the result in the Study tab.
* **Frontend.** The generate dialog defaults to AI when the provider is connected, adds short answers and an AI-grading switch for AI quizzes, and tracks jobs in `studyJobsProvider` (shown in the Study panel with progress, cancel, and failure messages).
* **Prompt checks.** `tests/test_study_integration.py` (`@pytest.mark.integration`) runs the three prompts against the configured provider and skips when it is unreachable.

## 9.10 Implementation Notes

* **E2E.** `tests/e2e/test_study_flow.py` uploads notes, ingests them through the real wiki engine with a mock LLM that answers the ingest and study prompts, then covers the offline flow (deck, review, quiz attempt, page edit marking items out of date, refresh, Anki export, backup/import keeping review state and attempts) and the AI flow (hybrid deck job, LLM quiz with AI-graded short answer, `/flashcards` over the chat WebSocket). It runs in the regular CI suite and the nightly E2E job.
* **Docs.** `docs/troubleshooting.md` covers empty decks/quizzes, unavailable AI options, failed or lost AI jobs, self-review of short answers, out-of-date items, and Anki import.

---

## Decisions Log

| # | Question | Decision |
|---|---|---|
| 1 | Review scheduling | In-house SM-2; no `fsrs` dependency |
| 2 | Behaviour when source pages change | Flag cards/questions as out of date; no automatic regeneration |
| 3 | Native Anki `.apkg` export | Preferred but not required; stretch item behind optional `anki` extra, CSV/TSV is the baseline |
| 4 | AI grading of short answers | On by default, per-quiz toggle, self-grading fallback |
| 5 | Where study items are stored | Database only; not committed to the wiki git repo |
