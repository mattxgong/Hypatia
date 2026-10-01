"""Study prompts against the configured real LLM (nightly / manual; skipped when unreachable)."""

from __future__ import annotations

import pytest

from app.dependencies import check_llm_available
from app.errors import HypatiaError
from app.models.db_models import CardType, QuestionType
from app.services.study.extractors import parse_page
from app.services.study.llm_generator import (
    generate_cards_with_llm,
    generate_questions_with_llm,
    grade_short_answer,
)

pytestmark = pytest.mark.integration

_PAGE = parse_page(
    "pages/concept/viterbi-algorithm.md",
    "Viterbi Algorithm",
    "concept",
    """---
title: "Viterbi Algorithm"
type: concept
---

## Definition

The Viterbi algorithm is a dynamic program that finds the most probable sequence of \
hidden states in a hidden Markov model.[source](hypatia://cite?file=hmm.pdf&page=3)

## Complexity

For a sequence of length \\(m\\) with \\(k\\) states it runs in \\(O(mk^2)\\) time.\
[source](hypatia://cite?file=hmm.pdf&page=4)
""",
)


@pytest.fixture(autouse=True)
async def require_llm() -> None:
    try:
        await check_llm_available()
    except HypatiaError as e:
        pytest.skip(f"LLM not reachable: {e.detail}")


async def test_flashcard_prompt_yields_cited_cards() -> None:
    cards = await generate_cards_with_llm(
        [_PAGE], count=4, card_types=[CardType.BASIC, CardType.CLOZE]
    )
    assert 1 <= len(cards) <= 4
    assert all(c.page_path == _PAGE.path and c.front and c.back for c in cards)


async def test_quiz_prompt_yields_valid_questions() -> None:
    questions = await generate_questions_with_llm(
        [_PAGE],
        count=4,
        question_types=[QuestionType.MCQ, QuestionType.TRUE_FALSE, QuestionType.SHORT],
        seed=1,
    )
    assert questions
    for q in questions:
        if q.question_type == QuestionType.MCQ:
            assert q.choices is not None
            assert 0 <= q.answer["choice"] < len(q.choices["options"])


async def test_grading_prompt_separates_right_from_wrong() -> None:
    reference = "The most probable sequence of hidden states."
    right = await grade_short_answer(
        "What does the Viterbi algorithm find?", reference, None, "the likeliest hidden state path"
    )
    wrong = await grade_short_answer(
        "What does the Viterbi algorithm find?", reference, None, "the boiling point of water"
    )
    assert right is not None and wrong is not None
    assert right.score > wrong.score
