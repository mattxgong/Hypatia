"""Deterministic grading for heuristic quiz questions (Task 9.3)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from app.models.db_models import QuestionType

GradeStatus = Literal["graded", "unanswered", "needs_self_review"]

_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+")


@dataclass(frozen=True)
class GradeResult:
    score: float
    correct: bool | None
    status: GradeStatus


def normalize_answer(text: str) -> str:
    """Case, accent, punctuation, article, and plural-insensitive form of a typed answer."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    words = re.sub(r"[^\w]+", " ", folded.lower()).split()
    normalized = _ARTICLE_RE.sub("", " ".join(words))
    if normalized.endswith("s") and not normalized.endswith("ss"):
        normalized = normalized[:-1]
    return normalized


def _result(correct: bool) -> GradeResult:
    return GradeResult(score=1.0 if correct else 0.0, correct=correct, status="graded")


def grade(question_type: QuestionType, answer: dict[str, Any], response: Any) -> GradeResult:
    """Score one response in [0, 1]. Malformed responses count as wrong, not as errors.

    Short answers are left as ``needs_self_review`` here; AI grading happens in the service.
    """
    if not isinstance(response, dict) or not response:
        return GradeResult(score=0.0, correct=False, status="unanswered")

    if question_type == QuestionType.MCQ:
        return _result(response.get("choice") == answer.get("choice"))

    if question_type == QuestionType.TRUE_FALSE:
        value = response.get("value")
        return _result(isinstance(value, bool) and value == answer.get("value"))

    if question_type == QuestionType.FILL:
        text = response.get("text")
        if not isinstance(text, str) or not text.strip():
            return GradeResult(score=0.0, correct=False, status="unanswered")
        accepted = {normalize_answer(a) for a in answer.get("accepted", [])}
        return _result(normalize_answer(text) in accepted)

    if question_type == QuestionType.MATCHING:
        expected = answer.get("pairs", [])
        given = response.get("pairs")
        if not isinstance(given, list) or not expected:
            return GradeResult(score=0.0, correct=False, status="unanswered")
        hits = sum(1 for i, target in enumerate(expected) if i < len(given) and given[i] == target)
        return GradeResult(
            score=hits / len(expected), correct=hits == len(expected), status="graded"
        )

    self_grade = response.get("self_grade")
    if isinstance(self_grade, bool):
        return _result(self_grade)
    text = response.get("text")
    if not isinstance(text, str) or not text.strip():
        return GradeResult(score=0.0, correct=False, status="unanswered")
    return GradeResult(score=0.0, correct=None, status="needs_self_review")
