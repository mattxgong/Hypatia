"""Tutoring through a submitted quiz attempt's mistakes (Phase 11.1, `/review-quiz`).

Only questions answered wrongly, partly wrongly or skipped go to the LLM, with
the cited wiki pages as context. Short answers still waiting for the student's
own check aren't graded yet, so they are left out.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ResourceNotFoundError
from app.models.db_models import QuestionType, Quiz, QuizAttempt, QuizQuestion, WikiPage
from app.services.prompts.review_prompt import REVIEW_SYSTEM_PROMPT
from app.services.wiki_engine import (
    _count_tokens,
    _llm,
    _output_budget,
    _prompt_budget,
    _truncate_to_tokens,
)

NO_MISTAKES_ANSWER = "You got every question right, so there are no mistakes to review."
_NO_ANSWER = "(no answer)"
# Mistakes come first; pages get what is left, but never more than this share.
_PAGES_RATIO = 0.7


@dataclass(frozen=True)
class Mistake:
    number: int
    question: QuizQuestion
    response: dict[str, Any] | None
    score: float
    feedback: str | None


def find_mistakes(questions: Sequence[QuizQuestion], attempt: QuizAttempt) -> list[Mistake]:
    """Questions scored below full marks, in quiz order. Unchecked short answers are skipped."""
    mistakes = []
    for number, question in enumerate(questions, 1):
        graded = attempt.grading_json.get(str(question.id), {})
        status = graded.get("status", "unanswered")
        score = float(graded.get("score", 0.0))
        if status == "needs_self_review" or (status == "graded" and score >= 1.0):
            continue
        response = attempt.answers_json.get(str(question.id))
        mistakes.append(
            Mistake(number, question, response if response else None, score, graded.get("feedback"))
        )
    return mistakes


def _option(options: list[Any], index: Any) -> str:
    if isinstance(index, int) and 0 <= index < len(options):
        return str(options[index])
    return _NO_ANSWER


def _pairs(choices: dict[str, Any], pairs: Any) -> str:
    left, right = choices.get("left", []), choices.get("right", [])
    if not isinstance(pairs, list):
        return _NO_ANSWER
    return "; ".join(
        f"{term} -> {_option(right, pairs[i] if i < len(pairs) else None)}"
        for i, term in enumerate(left)
    )


def _answers(question: QuizQuestion, response: dict[str, Any] | None) -> tuple[str, str]:
    """The student's answer and the correct one, as readable text."""
    response = response or {}
    expected = question.answer_json
    choices = question.choices_json or {}
    match question.question_type:
        case QuestionType.MCQ:
            options = choices.get("options", [])
            return _option(options, response.get("choice")), _option(
                options, expected.get("choice")
            )
        case QuestionType.TRUE_FALSE:
            value = response.get("value")
            given = str(value).lower() if isinstance(value, bool) else _NO_ANSWER
            return given, str(expected.get("value")).lower()
        case QuestionType.FILL:
            return str(response.get("text") or _NO_ANSWER), " or ".join(
                expected.get("accepted", [])
            )
        case QuestionType.MATCHING:
            return _pairs(choices, response.get("pairs")), _pairs(choices, expected.get("pairs"))
        case _:
            correct = str(expected.get("reference", ""))
            if rubric := expected.get("rubric"):
                correct += f"\nKey points: {rubric}"
            return str(response.get("text") or _NO_ANSWER), correct


def format_mistake(mistake: Mistake) -> str:
    question = mistake.question
    given, correct = _answers(question, mistake.response)
    earned = mistake.score * question.points
    lines = [
        (
            f"### Question {mistake.number} ({question.question_type.value}, "
            f"scored {earned:g} of {question.points})"
        ),
        question.prompt,
        f"**Student's answer:** {given}",
        f"**Correct answer:** {correct}",
    ]
    if question.explanation:
        lines.append(f"**Explanation:** {question.explanation}")
    if mistake.feedback:
        lines.append(f"**Grader feedback:** {mistake.feedback}")
    return "\n\n".join(lines)


async def load_attempt(
    session: AsyncSession, class_id: uuid.UUID, attempt_id: uuid.UUID
) -> tuple[Quiz, QuizAttempt, list[QuizQuestion]]:
    row = (
        await session.execute(
            select(QuizAttempt, Quiz)
            .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
            .where(QuizAttempt.id == attempt_id, Quiz.class_id == class_id)
        )
    ).first()
    if row is None:
        raise ResourceNotFoundError(f"Quiz attempt {attempt_id} not found")
    attempt, quiz = row
    questions = (
        await session.scalars(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == quiz.id)
            .order_by(QuizQuestion.position)
        )
    ).all()
    return quiz, attempt, list(questions)


async def _page_context(
    session: AsyncSession, class_id: uuid.UUID, mistakes: list[Mistake], budget: int
) -> tuple[list[str], list[str]]:
    paths = list(dict.fromkeys(p for m in mistakes for p in (m.question.page_hashes or {})))
    if not paths:
        return [], []
    rows = {
        page.path: page
        for page in await session.scalars(
            select(WikiPage).where(WikiPage.class_id == class_id, WikiPage.path.in_(paths))
        )
    }
    blocks, included = [], []
    for path in paths:
        page = rows.get(path)
        if page is None:
            continue  # deleted since the quiz was made
        tokens = _count_tokens(page.content)
        if tokens > budget:
            continue
        blocks.append(f"## Page: {page.title}\nPath: {page.path}\n\n{page.content}")
        included.append(path)
        budget -= tokens
    return blocks, included


async def review_stream(
    session: AsyncSession,
    class_id: uuid.UUID,
    attempt_id: uuid.UUID,
    *,
    consulted: list[str] | None = None,
) -> AsyncIterator[str]:
    """Stream the tutor's first message. ``consulted`` gets the pages it was given."""
    quiz, attempt, questions = await load_attempt(session, class_id, attempt_id)
    mistakes = find_mistakes(questions, attempt)
    if not mistakes:
        yield NO_MISTAKES_ANSWER
        return

    budget = _prompt_budget(REVIEW_SYSTEM_PROMPT)
    mistakes_text = _truncate_to_tokens(
        "\n\n---\n\n".join(format_mistake(m) for m in mistakes), int(budget * (1 - _PAGES_RATIO))
    )
    pages, included = await _page_context(
        session, class_id, mistakes, budget - _count_tokens(mistakes_text)
    )
    if consulted is not None:
        consulted.extend(included)

    user_prompt = f"## Quiz: {quiz.name}\n\n## Mistakes\n\n{mistakes_text}"
    if pages:
        user_prompt += "\n\n---\n\n## Wiki pages\n\n" + "\n\n---\n\n".join(pages)
    async with _llm() as provider:
        async for chunk in provider.stream(
            REVIEW_SYSTEM_PROMPT, user_prompt, max_tokens=_output_budget()
        ):
            yield chunk
