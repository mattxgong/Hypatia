"""Study router: flashcard decks, spaced-repetition review, and practice quizzes (Phase 9)."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import check_llm_available
from app.errors import ResourceNotFoundError
from app.models.db_models import (
    CardOrigin,
    Deck,
    Flashcard,
    Quiz,
    QuizAttempt,
    QuizQuestion,
    StudyMethod,
)
from app.models.schemas import (
    AttemptSelfGrade,
    DeckCreate,
    DeckExportFormat,
    DeckGenerateRequest,
    DeckRead,
    DeckRefreshResponse,
    DeckUpdate,
    FlashcardCreate,
    FlashcardRead,
    FlashcardReview,
    FlashcardUpdate,
    QuestionResultRead,
    QuizAttemptCreate,
    QuizAttemptRead,
    QuizGenerateRequest,
    QuizQuestionRead,
    QuizRead,
    QuizSummaryRead,
    StudyTaskStarted,
)
from app.services.study import jobs, service
from app.utils.logging import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/classes/{class_id}", tags=["study"])

_DEFAULT_DUE_LIMIT = 20


def _now() -> datetime:
    return datetime.now(UTC)


async def _get_deck(session: AsyncSession, class_id: uuid.UUID, deck_id: uuid.UUID) -> Deck:
    deck = await session.get(Deck, deck_id)
    if deck is None or deck.class_id != class_id:
        raise ResourceNotFoundError("Deck not found")
    return deck


async def _get_card(session: AsyncSession, deck: Deck, card_id: uuid.UUID) -> Flashcard:
    card = await session.get(Flashcard, card_id)
    if card is None or card.deck_id != deck.id:
        raise ResourceNotFoundError("Flashcard not found")
    return card


async def _get_quiz(session: AsyncSession, class_id: uuid.UUID, quiz_id: uuid.UUID) -> Quiz:
    quiz = await session.get(Quiz, quiz_id)
    if quiz is None or quiz.class_id != class_id:
        raise ResourceNotFoundError("Quiz not found")
    return quiz


def _card_read(card: Flashcard, stale: bool) -> FlashcardRead:
    return FlashcardRead(
        id=card.id,
        deck_id=card.deck_id,
        card_type=card.card_type,
        front=card.front,
        back=card.back,
        origin=card.origin,
        page_paths=list(card.page_hashes or {}),
        source_file_ids=list(card.source_file_ids or []),
        stale=stale,
        ease=card.ease,
        interval_days=card.interval_days,
        repetitions=card.repetitions,
        lapses=card.lapses,
        due_at=card.due_at,
        last_reviewed_at=card.last_reviewed_at,
        created_at=card.created_at,
        updated_at=card.updated_at,
    )


async def _card_reads(
    session: AsyncSession, class_id: uuid.UUID, cards: list[Flashcard]
) -> list[FlashcardRead]:
    current = await service.current_hashes(session, class_id, service.referenced_paths(cards))
    return [_card_read(c, service.is_stale(c.page_hashes, current)) for c in cards]


async def _deck_reads(
    session: AsyncSession, class_id: uuid.UUID, decks: list[Deck]
) -> list[DeckRead]:
    counts = await service.deck_counts(session, class_id, [d.id for d in decks], _now())
    return [
        DeckRead(
            id=d.id,
            class_id=d.class_id,
            name=d.name,
            description=d.description,
            generation_method=d.generation_method,
            scope_json=d.scope_json,
            card_count=counts[d.id][0],
            due_count=counts[d.id][1],
            stale_count=counts[d.id][2],
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in decks
    ]


async def _quiz_summary(
    session: AsyncSession, class_id: uuid.UUID, quiz: Quiz
) -> tuple[QuizSummaryRead, list[QuizQuestion], dict[str, str]]:
    questions = await service.quiz_questions(session, quiz.id)
    attempts = await service.quiz_attempts(session, quiz.id)
    current = await service.current_hashes(session, class_id, service.referenced_paths(questions))
    latest = attempts[0] if attempts else None
    summary = QuizSummaryRead(
        id=quiz.id,
        class_id=quiz.class_id,
        name=quiz.name,
        generation_method=quiz.generation_method,
        scope_json=quiz.scope_json,
        settings_json=quiz.settings_json,
        question_count=len(questions),
        stale_count=sum(1 for q in questions if service.is_stale(q.page_hashes, current)),
        attempt_count=len(attempts),
        last_score=latest.score if latest else None,
        last_max_score=latest.max_score if latest else None,
        created_at=quiz.created_at,
        updated_at=quiz.updated_at,
    )
    return summary, questions, current


async def _quiz_read(session: AsyncSession, class_id: uuid.UUID, quiz: Quiz) -> QuizRead:
    summary, questions, current = await _quiz_summary(session, class_id, quiz)
    return QuizRead(
        **summary.model_dump(),
        questions=[
            QuizQuestionRead(
                id=q.id,
                position=q.position,
                question_type=q.question_type,
                prompt=q.prompt,
                choices=q.choices_json,
                page_paths=list(q.page_hashes or {}),
                stale=service.is_stale(q.page_hashes, current),
            )
            for q in questions
        ],
    )


def _attempt_read(attempt: QuizAttempt, questions: list[QuizQuestion]) -> QuizAttemptRead:
    results = []
    for question in questions:
        key = str(question.id)
        graded = attempt.grading_json.get(key, {})
        results.append(
            QuestionResultRead(
                question_id=question.id,
                score=graded.get("score", 0.0),
                correct=graded.get("correct"),
                status=graded.get("status", "unanswered"),
                response=attempt.answers_json.get(key),
                expected=question.answer_json,
                explanation=question.explanation,
                feedback=graded.get("feedback"),
                grader=graded.get("grader"),
            )
        )
    return QuizAttemptRead(
        id=attempt.id,
        quiz_id=attempt.quiz_id,
        score=attempt.score,
        max_score=attempt.max_score,
        results=results,
        created_at=attempt.created_at,
    )


# --- Decks ---


@router.get("/decks", response_model=list[DeckRead])
async def list_decks(
    class_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[DeckRead]:
    await service.get_class_or_404(session, class_id)
    result = await session.execute(
        select(Deck).where(Deck.class_id == class_id).order_by(Deck.created_at.desc())
    )
    return await _deck_reads(session, class_id, list(result.scalars().all()))


@router.post("/decks", response_model=DeckRead, status_code=status.HTTP_201_CREATED)
async def create_deck(
    class_id: uuid.UUID, body: DeckCreate, session: AsyncSession = Depends(get_session)
) -> DeckRead:
    await service.get_class_or_404(session, class_id)
    deck = Deck(
        class_id=class_id,
        name=body.name,
        description=body.description,
        generation_method=StudyMethod.HEURISTIC,
    )
    session.add(deck)
    await session.commit()
    await session.refresh(deck)
    return (await _deck_reads(session, class_id, [deck]))[0]


@router.post(
    "/decks/generate",
    response_model=DeckRead,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": StudyTaskStarted}},
)
async def generate_deck(
    class_id: uuid.UUID, body: DeckGenerateRequest, session: AsyncSession = Depends(get_session)
) -> DeckRead | JSONResponse:
    await service.get_class_or_404(session, class_id)
    if body.method != "heuristic":
        return await _start_ai_generation(session, class_id, "deck", body)
    deck = await service.generate_deck(session, class_id, body)
    logger.info("deck_generated", class_id=str(class_id), deck_id=str(deck.id))
    return (await _deck_reads(session, class_id, [deck]))[0]


async def _start_ai_generation(
    session: AsyncSession,
    class_id: uuid.UUID,
    kind: jobs.StudyKind,
    body: DeckGenerateRequest | QuizGenerateRequest,
) -> JSONResponse:
    await service.ensure_scope_has_pages(session, class_id, body.scope)
    await check_llm_available()
    task_id = jobs.start_generation(kind, class_id, body)
    logger.info("study_generation_started", class_id=str(class_id), kind=kind, task_id=task_id)
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=StudyTaskStarted(task_id=task_id, kind=kind).model_dump(),
    )


@router.get("/decks/{deck_id}", response_model=DeckRead)
async def get_deck(
    class_id: uuid.UUID, deck_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> DeckRead:
    deck = await _get_deck(session, class_id, deck_id)
    return (await _deck_reads(session, class_id, [deck]))[0]


@router.patch("/decks/{deck_id}", response_model=DeckRead)
async def update_deck(
    class_id: uuid.UUID,
    deck_id: uuid.UUID,
    body: DeckUpdate,
    session: AsyncSession = Depends(get_session),
) -> DeckRead:
    deck = await _get_deck(session, class_id, deck_id)
    if body.name is not None:
        deck.name = body.name
    if body.description is not None:
        deck.description = body.description
    await session.commit()
    await session.refresh(deck)
    return (await _deck_reads(session, class_id, [deck]))[0]


@router.delete("/decks/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deck(
    class_id: uuid.UUID, deck_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> None:
    deck = await _get_deck(session, class_id, deck_id)
    await session.delete(deck)
    await session.commit()


@router.post("/decks/{deck_id}/refresh", response_model=DeckRefreshResponse)
async def refresh_deck(
    class_id: uuid.UUID, deck_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> DeckRefreshResponse:
    deck = await _get_deck(session, class_id, deck_id)
    result = await service.refresh_stale_cards(session, class_id, deck)
    return DeckRefreshResponse(
        updated=result.updated, removed=result.removed, remaining_stale=result.remaining_stale
    )


@router.get("/decks/{deck_id}/export")
async def export_deck(
    class_id: uuid.UUID,
    deck_id: uuid.UUID,
    format: DeckExportFormat = Query("csv"),  # noqa: B008
    session: AsyncSession = Depends(get_session),
) -> Response:
    deck = await _get_deck(session, class_id, deck_id)
    body = service.export_deck(deck, await service.deck_cards(session, deck.id), format)
    stem = re.sub(r"[^\w\-]+", "-", deck.name).strip("-") or "deck"
    filename, media_type = (
        (f"{stem}.csv", "text/csv") if format == "csv" else (f"{stem}.anki.txt", "text/plain")
    )
    return Response(
        content=body,
        media_type=f"{media_type}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Flashcards ---


@router.get("/decks/{deck_id}/cards", response_model=list[FlashcardRead])
async def list_cards(
    class_id: uuid.UUID, deck_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[FlashcardRead]:
    deck = await _get_deck(session, class_id, deck_id)
    return await _card_reads(session, class_id, await service.deck_cards(session, deck.id))


@router.get("/decks/{deck_id}/due", response_model=list[FlashcardRead])
async def list_due_cards(
    class_id: uuid.UUID,
    deck_id: uuid.UUID,
    limit: int = Query(_DEFAULT_DUE_LIMIT, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[FlashcardRead]:
    deck = await _get_deck(session, class_id, deck_id)
    result = await session.execute(
        select(Flashcard)
        .where(Flashcard.deck_id == deck.id, Flashcard.due_at <= _now())
        .order_by(Flashcard.due_at, Flashcard.created_at)
        .limit(limit)
    )
    return await _card_reads(session, class_id, list(result.scalars().all()))


@router.post(
    "/decks/{deck_id}/cards", response_model=FlashcardRead, status_code=status.HTTP_201_CREATED
)
async def create_card(
    class_id: uuid.UUID,
    deck_id: uuid.UUID,
    body: FlashcardCreate,
    session: AsyncSession = Depends(get_session),
) -> FlashcardRead:
    deck = await _get_deck(session, class_id, deck_id)
    card = Flashcard(
        deck_id=deck.id,
        card_type=body.card_type,
        front=body.front,
        back=body.back,
        origin=CardOrigin.USER,
    )
    session.add(card)
    await session.commit()
    await session.refresh(card)
    return _card_read(card, stale=False)


@router.patch("/decks/{deck_id}/cards/{card_id}", response_model=FlashcardRead)
async def update_card(
    class_id: uuid.UUID,
    deck_id: uuid.UUID,
    card_id: uuid.UUID,
    body: FlashcardUpdate,
    session: AsyncSession = Depends(get_session),
) -> FlashcardRead:
    deck = await _get_deck(session, class_id, deck_id)
    card = await _get_card(session, deck, card_id)
    if body.front is not None:
        card.front = body.front
    if body.back is not None:
        card.back = body.back
    if body.acknowledge_changes:
        card.page_hashes = await service.snapshot_pages(session, class_id, card)
    await session.commit()
    await session.refresh(card)
    return (await _card_reads(session, class_id, [card]))[0]


@router.delete("/decks/{deck_id}/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(
    class_id: uuid.UUID,
    deck_id: uuid.UUID,
    card_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    deck = await _get_deck(session, class_id, deck_id)
    card = await _get_card(session, deck, card_id)
    await session.delete(card)
    await session.commit()


@router.post("/decks/{deck_id}/cards/{card_id}/review", response_model=FlashcardRead)
async def review_card(
    class_id: uuid.UUID,
    deck_id: uuid.UUID,
    card_id: uuid.UUID,
    body: FlashcardReview,
    session: AsyncSession = Depends(get_session),
) -> FlashcardRead:
    deck = await _get_deck(session, class_id, deck_id)
    card = await _get_card(session, deck, card_id)
    service.apply_review(card, body.rating, _now())
    await session.commit()
    await session.refresh(card)
    return (await _card_reads(session, class_id, [card]))[0]


# --- Quizzes ---


@router.get("/quizzes", response_model=list[QuizSummaryRead])
async def list_quizzes(
    class_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[QuizSummaryRead]:
    await service.get_class_or_404(session, class_id)
    result = await session.execute(
        select(Quiz).where(Quiz.class_id == class_id).order_by(Quiz.created_at.desc())
    )
    return [(await _quiz_summary(session, class_id, q))[0] for q in result.scalars().all()]


@router.post(
    "/quizzes/generate",
    response_model=QuizRead,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": StudyTaskStarted}},
)
async def generate_quiz(
    class_id: uuid.UUID, body: QuizGenerateRequest, session: AsyncSession = Depends(get_session)
) -> QuizRead | JSONResponse:
    await service.get_class_or_404(session, class_id)
    if body.method != "heuristic":
        return await _start_ai_generation(session, class_id, "quiz", body)
    quiz = await service.generate_quiz(session, class_id, body)
    logger.info("quiz_generated", class_id=str(class_id), quiz_id=str(quiz.id))
    return await _quiz_read(session, class_id, quiz)


@router.get("/quizzes/{quiz_id}", response_model=QuizRead)
async def get_quiz(
    class_id: uuid.UUID, quiz_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> QuizRead:
    quiz = await _get_quiz(session, class_id, quiz_id)
    return await _quiz_read(session, class_id, quiz)


@router.delete("/quizzes/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quiz(
    class_id: uuid.UUID, quiz_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> None:
    quiz = await _get_quiz(session, class_id, quiz_id)
    await session.delete(quiz)
    await session.commit()


@router.post(
    "/quizzes/{quiz_id}/attempts",
    response_model=QuizAttemptRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_attempt(
    class_id: uuid.UUID,
    quiz_id: uuid.UUID,
    body: QuizAttemptCreate,
    session: AsyncSession = Depends(get_session),
) -> QuizAttemptRead:
    quiz = await _get_quiz(session, class_id, quiz_id)
    questions = await service.quiz_questions(session, quiz.id)
    attempt = await service.grade_attempt(quiz, questions, body.answers)
    session.add(attempt)
    await session.commit()
    await session.refresh(attempt)
    return _attempt_read(attempt, questions)


@router.patch("/quizzes/{quiz_id}/attempts/{attempt_id}", response_model=QuizAttemptRead)
async def self_grade_attempt(
    class_id: uuid.UUID,
    quiz_id: uuid.UUID,
    attempt_id: uuid.UUID,
    body: AttemptSelfGrade,
    session: AsyncSession = Depends(get_session),
) -> QuizAttemptRead:
    quiz = await _get_quiz(session, class_id, quiz_id)
    attempt = await session.get(QuizAttempt, attempt_id)
    if attempt is None or attempt.quiz_id != quiz.id:
        raise ResourceNotFoundError("Quiz attempt not found")
    questions = await service.quiz_questions(session, quiz.id)
    service.apply_self_grades(attempt, questions, body.grades)
    await session.commit()
    await session.refresh(attempt)
    return _attempt_read(attempt, questions)


@router.get("/quizzes/{quiz_id}/attempts", response_model=list[QuizAttemptRead])
async def list_attempts(
    class_id: uuid.UUID, quiz_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[QuizAttemptRead]:
    quiz = await _get_quiz(session, class_id, quiz_id)
    questions = await service.quiz_questions(session, quiz.id)
    return [_attempt_read(a, questions) for a in await service.quiz_attempts(session, quiz.id)]
