"""Choosing and describing quiz mistakes for /review-quiz (Phase 11.1)."""

from __future__ import annotations

import uuid
from typing import Any

from app.models.db_models import QuestionType, QuizAttempt, QuizQuestion
from app.services.study.mistake_review import find_mistakes, format_mistake


def _question(
    qtype: QuestionType, prompt: str, answer: dict[str, Any], **extra: Any
) -> QuizQuestion:
    return QuizQuestion(
        id=uuid.uuid4(),
        position=0,
        question_type=qtype,
        prompt=prompt,
        answer_json=answer,
        points=extra.pop("points", 1),
        **extra,
    )


def _attempt(
    entries: dict[QuizQuestion, tuple[dict[str, Any] | None, dict[str, Any]]],
) -> QuizAttempt:
    return QuizAttempt(
        answers_json={str(q.id): r for q, (r, _) in entries.items() if r is not None},
        grading_json={str(q.id): g for q, (_, g) in entries.items()},
        score=0,
        max_score=len(entries),
    )


def test_only_wrong_partial_and_skipped_questions_are_mistakes() -> None:
    right = _question(QuestionType.TRUE_FALSE, "Right", {"value": True})
    wrong = _question(QuestionType.TRUE_FALSE, "Wrong", {"value": True})
    partial = _question(QuestionType.MATCHING, "Partial", {"pairs": [0, 1]})
    skipped = _question(QuestionType.FILL, "Skipped", {"accepted": ["x"]})
    unchecked = _question(QuestionType.SHORT, "Unchecked", {"reference": "r"})
    attempt = _attempt(
        {
            right: ({"value": True}, {"score": 1.0, "correct": True, "status": "graded"}),
            wrong: ({"value": False}, {"score": 0.0, "correct": False, "status": "graded"}),
            partial: ({"pairs": [0, 0]}, {"score": 0.5, "correct": False, "status": "graded"}),
            skipped: (None, {"score": 0.0, "correct": False, "status": "unanswered"}),
            unchecked: (
                {"text": "t"},
                {"score": 0.0, "correct": None, "status": "needs_self_review"},
            ),
        }
    )

    mistakes = find_mistakes([right, wrong, partial, skipped, unchecked], attempt)

    assert [m.question.prompt for m in mistakes] == ["Wrong", "Partial", "Skipped"]
    assert [m.number for m in mistakes] == [2, 3, 4]


def test_mistakes_read_as_text_with_both_answers() -> None:
    mcq = _question(
        QuestionType.MCQ,
        "What does Viterbi find?",
        {"choice": 1},
        choices_json={"options": ["Marginals", "The best path", "Tokens"]},
        explanation="It maximizes over paths.",
        points=2,
    )
    matching = _question(
        QuestionType.MATCHING,
        "Match.",
        {"pairs": [1, 0]},
        choices_json={"left": ["HMM", "CRF"], "right": ["discriminative", "generative"]},
    )
    attempt = _attempt(
        {
            mcq: ({"choice": 0}, {"score": 0.0, "status": "graded", "feedback": None}),
            matching: ({"pairs": [0, 0]}, {"score": 0.5, "status": "graded"}),
        }
    )

    first, second = (format_mistake(m) for m in find_mistakes([mcq, matching], attempt))

    assert "scored 0 of 2" in first
    assert "**Student's answer:** Marginals" in first
    assert "**Correct answer:** The best path" in first
    assert "**Explanation:** It maximizes over paths." in first
    assert "HMM -> discriminative; CRF -> discriminative" in second
    assert "HMM -> generative; CRF -> discriminative" in second


def test_a_skipped_short_answer_shows_the_reference_and_rubric() -> None:
    short = _question(QuestionType.SHORT, "Why?", {"reference": "Because.", "rubric": "Says why."})
    attempt = _attempt({short: (None, {"score": 0.0, "status": "unanswered"})})

    [text] = (format_mistake(m) for m in find_mistakes([short], attempt))

    assert "**Student's answer:** (no answer)" in text
    assert "**Correct answer:** Because.\nKey points: Says why." in text
