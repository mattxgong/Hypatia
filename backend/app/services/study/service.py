"""Study service: scope resolution, generation, staleness, review, and export (Phase 9)."""

from __future__ import annotations

import asyncio
import csv
import io
import random
import re
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ErrorCode, HypatiaError, ResourceNotFoundError
from app.models.db_models import (
    CardOrigin,
    CardType,
    Class,
    Deck,
    File,
    Flashcard,
    QuestionType,
    Quiz,
    QuizAttempt,
    QuizQuestion,
    StudyMethod,
    WikiCategory,
    WikiPage,
)
from app.models.schemas import (
    DeckExportFormat,
    DeckGenerateRequest,
    QuizGenerateRequest,
    StudyScope,
)
from app.services.study import llm_generator
from app.services.study.extractors import (
    CardCandidate,
    PageDoc,
    body_hash,
    generate_cards,
    normalize_text,
    parse_page,
    resolve_wiki_links,
    slug_for_path,
)
from app.services.study.grading import grade
from app.services.study.quiz_builder import QuestionDraft, build_quiz, cloze_prompt
from app.services.study.scheduler import Rating, ReviewState, review
from app.services.task_manager import task_manager
from app.services.wiki_search import hybrid_search

_STUDY_CATEGORIES = (
    WikiCategory.CONCEPT,
    WikiCategory.ENTITY,
    WikiCategory.SYNTHESIS,
    WikiCategory.SOURCE_SUMMARY,
)
_TITLE_CATEGORIES = (WikiCategory.CONCEPT, WikiCategory.ENTITY)
_TOPIC_PAGE_LIMIT = 15
_CITATION_RE = re.compile(r"\[[^\]]*\]\(hypatia://[^)]*\)")
_NO_CONTENT_ACTION = (
    "Add sources so the wiki has concept pages, or widen the scope to the whole class."
)


@dataclass(frozen=True)
class RefreshResult:
    updated: int
    removed: int
    remaining_stale: int


async def get_class_or_404(session: AsyncSession, class_id: uuid.UUID) -> Class:
    class_ = await session.get(Class, class_id)
    if class_ is None:
        raise ResourceNotFoundError("Class not found")
    return class_


async def _class_pages(session: AsyncSession, class_id: uuid.UUID) -> list[WikiPage]:
    result = await session.execute(
        select(WikiPage)
        .where(WikiPage.class_id == class_id, WikiPage.category.in_(_STUDY_CATEGORIES))
        .order_by(WikiPage.path)
    )
    return list(result.scalars().all())


async def resolve_scope(
    session: AsyncSession, class_id: uuid.UUID, scope: StudyScope
) -> tuple[list[WikiPage], str]:
    """Return the wiki pages a scope covers and a short human label for it."""
    if scope.type == "topic":
        query = scope.query or ""
        hits = await hybrid_search(session, class_id, query, limit=_TOPIC_PAGE_LIMIT)
        wanted = [h.path for h in hits]
        pages = {p.path: p for p in await _class_pages(session, class_id) if p.path in wanted}
        return [pages[p] for p in wanted if p in pages], query

    if scope.type == "pages":
        wanted = list(dict.fromkeys(scope.paths or []))
        pages = {p.path: p for p in await _class_pages(session, class_id) if p.path in wanted}
        selected = [pages[p] for p in wanted if p in pages]
        label = selected[0].title if len(selected) == 1 else f"{len(selected)} pages"
        return selected, label

    if scope.type == "file":
        file_record = await session.get(File, scope.file_id)
        if file_record is None or file_record.class_id != class_id:
            raise ResourceNotFoundError("Source file not found")
        file_key = str(scope.file_id)
        linked = [
            p
            for p in await _class_pages(session, class_id)
            if file_key in (p.source_file_ids or [])
        ]
        return linked, file_record.original_filename

    return await _class_pages(session, class_id), "All pages"


async def slug_titles(session: AsyncSession, class_id: uuid.UUID) -> dict[str, str]:
    result = await session.execute(
        select(WikiPage.path, WikiPage.title).where(
            WikiPage.class_id == class_id, WikiPage.category.in_(_TITLE_CATEGORIES)
        )
    )
    return {slug_for_path(path): title for path, title in result.all()}


def _docs(pages: Iterable[WikiPage]) -> list[PageDoc]:
    return [
        parse_page(p.path, p.title, p.category.value, p.content, p.source_file_ids) for p in pages
    ]


async def current_hashes(
    session: AsyncSession, class_id: uuid.UUID, paths: Iterable[str]
) -> dict[str, str]:
    wanted = set(paths)
    if not wanted:
        return {}
    result = await session.execute(
        select(WikiPage.path, WikiPage.content).where(
            WikiPage.class_id == class_id, WikiPage.path.in_(wanted)
        )
    )
    return {path: body_hash(content) for path, content in result.all()}


def is_stale(page_hashes: dict[str, str] | None, current: dict[str, str]) -> bool:
    return any(current.get(path) != digest for path, digest in (page_hashes or {}).items())


def referenced_paths(items: Iterable[Flashcard | QuizQuestion]) -> set[str]:
    return {path for item in items for path in (item.page_hashes or {})}


def _no_content(kind: str) -> HypatiaError:
    return HypatiaError(
        ErrorCode.VALIDATION_ERROR,
        detail=f"No {kind} could be generated from the selected wiki pages.",
        user_action=_NO_CONTENT_ACTION,
    )


async def generate_deck(
    session: AsyncSession, class_id: uuid.UUID, request: DeckGenerateRequest
) -> Deck:
    pages, label = await resolve_scope(session, class_id, request.scope)
    candidates = generate_cards(
        _docs(pages),
        slug_titles=await slug_titles(session, class_id),
        card_types=request.card_types,
        limit=request.count,
    )
    return await _save_deck(session, class_id, request, label, pages, candidates)


async def ensure_scope_has_pages(
    session: AsyncSession, class_id: uuid.UUID, scope: StudyScope
) -> None:
    """Fail fast, before starting a background job, when a scope matches no pages."""
    pages, _ = await resolve_scope(session, class_id, scope)
    if not pages:
        raise _no_content("study material")


def _progress(task_id: str, noun: str) -> Callable[[int, int], None]:
    def report(done: int, total: int) -> None:
        task_manager.update_progress(
            task_id, done * 100 // max(total, 1), f"Writing {noun}: part {done + 1} of {total}"
        )

    return report


async def generate_deck_with_llm(
    session: AsyncSession, class_id: uuid.UUID, request: DeckGenerateRequest, task_id: str
) -> Deck:
    """LLM (or hybrid) deck generation; run as a task because it can take minutes."""
    pages, label = await resolve_scope(session, class_id, request.scope)
    docs = _docs(pages)
    drafts = (
        generate_cards(
            docs,
            slug_titles=await slug_titles(session, class_id),
            card_types=request.card_types,
        )
        if request.method == "hybrid"
        else []
    )
    candidates = await llm_generator.generate_cards_with_llm(
        docs,
        count=request.count,
        card_types=request.card_types,
        drafts=drafts,
        progress=_progress(task_id, "flashcards"),
        cancelled=lambda: task_manager.is_cancelled(task_id),
    )
    if task_manager.is_cancelled(task_id):
        raise llm_generator.GenerationCancelled
    return await _save_deck(session, class_id, request, label, pages, candidates)


async def _save_deck(
    session: AsyncSession,
    class_id: uuid.UUID,
    request: DeckGenerateRequest,
    label: str,
    pages: list[WikiPage],
    candidates: list[CardCandidate],
) -> Deck:
    if not candidates:
        raise _no_content("flashcards")
    hashes = {p.path: body_hash(p.content) for p in pages}
    origin = CardOrigin.HEURISTIC if request.method == "heuristic" else CardOrigin.LLM
    deck = Deck(
        class_id=class_id,
        name=request.name or f"{label} flashcards",
        generation_method=StudyMethod(request.method),
        scope_json=request.scope.model_dump(mode="json", exclude_none=True),
    )
    session.add(deck)
    await session.flush()
    for candidate in candidates:
        session.add(
            Flashcard(
                deck_id=deck.id,
                card_type=candidate.card_type,
                front=candidate.front,
                back=candidate.back,
                page_hashes={candidate.page_path: hashes[candidate.page_path]},
                source_file_ids=candidate.source_file_ids or None,
                origin=origin,
            )
        )
    await session.commit()
    await session.refresh(deck)
    return deck


async def generate_quiz(
    session: AsyncSession, class_id: uuid.UUID, request: QuizGenerateRequest
) -> Quiz:
    pages, label = await resolve_scope(session, class_id, request.scope)
    pool = generate_cards(_docs(pages), slug_titles=await slug_titles(session, class_id))
    seed = _seed(request)
    drafts = build_quiz(pool, question_types=request.question_types, count=request.count, seed=seed)
    return await _save_quiz(session, class_id, request, label, pages, drafts, seed)


def _seed(request: QuizGenerateRequest) -> int:
    return request.seed if request.seed is not None else random.SystemRandom().randrange(2**31)


async def generate_quiz_with_llm(
    session: AsyncSession, class_id: uuid.UUID, request: QuizGenerateRequest, task_id: str
) -> Quiz:
    pages, label = await resolve_scope(session, class_id, request.scope)
    docs = _docs(pages)
    key_facts = (
        generate_cards(docs, slug_titles=await slug_titles(session, class_id))
        if request.method == "hybrid"
        else []
    )
    seed = _seed(request)
    drafts = await llm_generator.generate_questions_with_llm(
        docs,
        count=request.count,
        question_types=request.question_types,
        seed=seed,
        key_facts=key_facts,
        progress=_progress(task_id, "questions"),
        cancelled=lambda: task_manager.is_cancelled(task_id),
    )
    if task_manager.is_cancelled(task_id):
        raise llm_generator.GenerationCancelled
    return await _save_quiz(session, class_id, request, label, pages, drafts, seed)


async def _save_quiz(
    session: AsyncSession,
    class_id: uuid.UUID,
    request: QuizGenerateRequest,
    label: str,
    pages: list[WikiPage],
    drafts: list[QuestionDraft],
    seed: int,
) -> Quiz:
    if not drafts:
        raise _no_content("quiz questions")
    hashes = {p.path: body_hash(p.content) for p in pages}
    quiz = Quiz(
        class_id=class_id,
        name=request.name or f"{label} quiz",
        generation_method=StudyMethod(request.method),
        scope_json=request.scope.model_dump(mode="json", exclude_none=True),
        settings_json={
            "count": request.count,
            "question_types": [t.value for t in request.question_types],
            "seed": seed,
            "ai_grading": request.ai_grading,
        },
    )
    session.add(quiz)
    await session.flush()
    for position, draft in enumerate(drafts):
        session.add(
            QuizQuestion(
                quiz_id=quiz.id,
                position=position,
                question_type=draft.question_type,
                prompt=draft.prompt,
                choices_json=draft.choices,
                answer_json=draft.answer,
                explanation=draft.explanation,
                page_hashes={path: hashes[path] for path in draft.page_paths},
                source_file_ids=draft.source_file_ids or None,
            )
        )
    await session.commit()
    await session.refresh(quiz)
    return quiz


def apply_review(card: Flashcard, rating: Rating, now: datetime) -> None:
    outcome = review(
        ReviewState(
            ease=card.ease,
            interval_days=card.interval_days,
            repetitions=card.repetitions,
            lapses=card.lapses,
        ),
        rating,
        now,
    )
    card.ease = outcome.state.ease
    card.interval_days = outcome.state.interval_days
    card.repetitions = outcome.state.repetitions
    card.lapses = outcome.state.lapses
    card.due_at = outcome.due_at
    card.last_reviewed_at = now


async def deck_cards(session: AsyncSession, deck_id: uuid.UUID) -> list[Flashcard]:
    result = await session.execute(
        select(Flashcard).where(Flashcard.deck_id == deck_id).order_by(Flashcard.created_at)
    )
    return list(result.scalars().all())


async def deck_counts(
    session: AsyncSession, class_id: uuid.UUID, deck_ids: Sequence[uuid.UUID], now: datetime
) -> dict[uuid.UUID, tuple[int, int, int]]:
    """``(card_count, due_count, stale_count)`` per deck."""
    if not deck_ids:
        return {}
    total_rows = await session.execute(
        select(Flashcard.deck_id, func.count())
        .where(Flashcard.deck_id.in_(deck_ids))
        .group_by(Flashcard.deck_id)
    )
    totals: dict[uuid.UUID, int] = {deck_id: n for deck_id, n in total_rows.all()}
    due_rows = await session.execute(
        select(Flashcard.deck_id, func.count())
        .where(Flashcard.deck_id.in_(deck_ids), Flashcard.due_at <= now)
        .group_by(Flashcard.deck_id)
    )
    due: dict[uuid.UUID, int] = {deck_id: n for deck_id, n in due_rows.all()}
    hash_rows = (
        await session.execute(
            select(Flashcard.deck_id, Flashcard.page_hashes).where(Flashcard.deck_id.in_(deck_ids))
        )
    ).all()
    current = await current_hashes(
        session, class_id, {path for _, hashes in hash_rows for path in (hashes or {})}
    )
    stale: dict[uuid.UUID, int] = {}
    for deck_id, hashes in hash_rows:
        if is_stale(hashes, current):
            stale[deck_id] = stale.get(deck_id, 0) + 1
    return {
        deck_id: (totals.get(deck_id, 0), due.get(deck_id, 0), stale.get(deck_id, 0))
        for deck_id in deck_ids
    }


async def refresh_stale_cards(
    session: AsyncSession, class_id: uuid.UUID, deck: Deck
) -> RefreshResult:
    """Re-extract out-of-date heuristic cards from the current pages.

    A card whose front still appears keeps its review history and gets the new
    back; one that no longer appears is removed. AI-written and user-written
    cards are left for the user to edit or acknowledge.
    """
    cards = await deck_cards(session, deck.id)
    current = await current_hashes(session, class_id, referenced_paths(cards))
    stale = [c for c in cards if is_stale(c.page_hashes, current)]
    regenerable = [c for c in stale if c.origin == CardOrigin.HEURISTIC]
    if not regenerable:
        return RefreshResult(0, 0, len(stale))

    page_paths = {p for c in regenerable for p in (c.page_hashes or {}) if p in current}
    pages = [p for p in await _class_pages(session, class_id) if p.path in page_paths]
    candidates = generate_cards(_docs(pages), slug_titles=await slug_titles(session, class_id))
    by_front = {normalize_text(c.front): c for c in candidates}

    updated = removed = 0
    for card in regenerable:
        match = by_front.get(normalize_text(card.front))
        if match is not None and match.card_type == card.card_type:
            card.back = match.back
            card.page_hashes = {match.page_path: current[match.page_path]}
            card.source_file_ids = match.source_file_ids or None
            updated += 1
        else:
            await session.delete(card)
            removed += 1
    await session.commit()
    return RefreshResult(updated, removed, len(stale) - updated - removed)


async def snapshot_pages(
    session: AsyncSession, class_id: uuid.UUID, card: Flashcard
) -> dict[str, str] | None:
    """Current hashes of the pages a card references; missing pages are dropped."""
    if not card.page_hashes:
        return card.page_hashes
    current = await current_hashes(session, class_id, card.page_hashes)
    return {path: current[path] for path in card.page_hashes if path in current} or None


def _export_text(text: str) -> str:
    return resolve_wiki_links(_CITATION_RE.sub("", text), {}).replace("**", "").strip()


def export_deck(deck: Deck, cards: Iterable[Flashcard], fmt: DeckExportFormat) -> str:
    """Render a deck as generic CSV (front, back) or an Anki-importable TSV."""
    buffer = io.StringIO()
    if fmt == "csv":
        writer = csv.writer(buffer)
        writer.writerow(["front", "back"])
        for card in cards:
            if card.card_type == CardType.CLOZE:
                writer.writerow([_export_text(cloze_prompt(card.front)), _export_text(card.back)])
            else:
                writer.writerow([_export_text(card.front), _export_text(card.back)])
        return buffer.getvalue()

    deck_name = " ".join(deck.name.split())
    buffer.write("#separator:tab\n#html:false\n#notetype column:1\n#tags column:4\n")
    buffer.write(f"#deck:{deck_name}\n")
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    for card in cards:
        if card.card_type == CardType.CLOZE:
            writer.writerow(["Cloze", _export_text(card.front), "", "hypatia"])
        else:
            writer.writerow(["Basic", _export_text(card.front), _export_text(card.back), "hypatia"])
    return buffer.getvalue()


async def quiz_questions(session: AsyncSession, quiz_id: uuid.UUID) -> list[QuizQuestion]:
    result = await session.execute(
        select(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id).order_by(QuizQuestion.position)
    )
    return list(result.scalars().all())


async def quiz_attempts(session: AsyncSession, quiz_id: uuid.UUID) -> list[QuizAttempt]:
    result = await session.execute(
        select(QuizAttempt)
        .where(QuizAttempt.quiz_id == quiz_id)
        .order_by(QuizAttempt.created_at.desc())
    )
    return list(result.scalars().all())


async def grade_attempt(
    quiz: Quiz, questions: Sequence[QuizQuestion], answers: dict[uuid.UUID, dict[str, Any]]
) -> QuizAttempt:
    """Grade every question; typed short answers go to the LLM when the quiz allows it."""
    by_id = {q.id: q for q in questions}
    answers_json = {str(qid): response for qid, response in answers.items() if qid in by_id}
    grading: dict[str, dict[str, Any]] = {}
    to_ai: list[QuizQuestion] = []
    ai_enabled = (quiz.settings_json or {}).get("ai_grading", True)
    for question in questions:
        response = answers.get(question.id)
        result = grade(question.question_type, question.answer_json, response)
        entry: dict[str, Any] = {
            "score": result.score,
            "correct": result.correct,
            "status": result.status,
        }
        if question.question_type == QuestionType.SHORT and result.status == "graded":
            entry["grader"] = "self"
        grading[str(question.id)] = entry
        if result.status == "needs_self_review" and ai_enabled:
            to_ai.append(question)

    ai_grades = await asyncio.gather(
        *(
            llm_generator.grade_short_answer(
                q.prompt,
                str(q.answer_json.get("reference", "")),
                q.answer_json.get("rubric"),
                str((answers.get(q.id) or {}).get("text", "")),
            )
            for q in to_ai
        )
    )
    for question, ai_grade in zip(to_ai, ai_grades, strict=True):
        if ai_grade is not None:
            grading[str(question.id)] = {
                "score": ai_grade.score,
                "correct": ai_grade.correct,
                "status": "graded",
                "grader": "ai",
                "feedback": ai_grade.feedback or None,
            }

    return QuizAttempt(
        quiz_id=quiz.id,
        answers_json=answers_json,
        grading_json=grading,
        score=sum(g["score"] for g in grading.values()),
        max_score=float(len(questions)),
    )


def apply_self_grades(
    attempt: QuizAttempt, questions: Sequence[QuizQuestion], grades: dict[uuid.UUID, bool]
) -> None:
    """Record the user's verdict on short answers; other question types keep their grade."""
    short_ids = {str(q.id) for q in questions if q.question_type == QuestionType.SHORT}
    grading = dict(attempt.grading_json)
    for question_id, correct in grades.items():
        key = str(question_id)
        if key not in short_ids:
            continue
        previous = grading.get(key, {})
        grading[key] = {
            "score": 1.0 if correct else 0.0,
            "correct": correct,
            "status": "graded",
            "grader": "self",
            "feedback": previous.get("feedback"),
        }
    attempt.grading_json = grading
    attempt.score = sum(g.get("score", 0.0) for g in grading.values())
