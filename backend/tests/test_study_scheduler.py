"""Spaced-repetition scheduling: Anki-style learning steps, then SM-2 (Task 9.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.study.scheduler import (
    DEFAULT_EASE,
    LEARNING_STEPS,
    MIN_EASE,
    RELEARN_DELAY,
    ReviewState,
    review,
)

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)
GRADUATED = ReviewState(learning_step=None)


def _run(state: ReviewState, *ratings: str) -> tuple[ReviewState, datetime]:
    outcome = None
    for rating in ratings:
        outcome = review(state, rating, NOW)  # type: ignore[arg-type]
        state = outcome.state
    assert outcome is not None
    return state, outcome.due_at


# ---------------------------------------------------------------------------
# Learning a new card
# ---------------------------------------------------------------------------


def test_new_card_goes_through_the_learning_steps():
    state, due = _run(ReviewState(), "good")
    assert (state.learning_step, due) == (1, NOW + LEARNING_STEPS[1])

    state, due = _run(state, "good")
    assert state.learning_step is None
    assert (state.interval_days, state.repetitions) == (1, 1)
    assert due == NOW + timedelta(days=1)


def test_again_while_learning_restarts_the_steps_without_an_ease_penalty():
    state, due = _run(ReviewState(), "good", "again")
    assert state.learning_step == 0
    assert due == NOW + LEARNING_STEPS[0]
    assert state.ease == DEFAULT_EASE
    assert state.lapses == 0


def test_hard_while_learning_repeats_the_step():
    state, due = _run(ReviewState(), "good", "hard")
    assert (state.learning_step, due) == (1, NOW + LEARNING_STEPS[1])
    assert state.ease == DEFAULT_EASE


def test_easy_graduates_a_new_card_to_four_days():
    state, due = _run(ReviewState(), "easy")
    assert state.learning_step is None
    assert (state.interval_days, state.ease) == (4, DEFAULT_EASE)
    assert due == NOW + timedelta(days=4)


def test_missing_a_brand_new_card_twice_leaves_its_ease_alone():
    state, _ = _run(ReviewState(), "again", "again", "good", "good")
    assert state.ease == DEFAULT_EASE
    assert state.interval_days == 1


# ---------------------------------------------------------------------------
# Reviewing a learned card (SM-2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ratings", "interval", "ease"),
    [
        (["good"], 6, 2.5),
        (["hard"], 3, 2.36),
        (["easy"], 8, 2.6),
        (["good", "good"], 15, 2.5),
        (["good", "hard"], 7, 2.36),
        (["good", "easy"], 20, 2.6),
    ],
)
def test_learned_card_intervals_and_ease(ratings: list[str], interval: int, ease: float) -> None:
    just_graduated = ReviewState(interval_days=1, repetitions=1, learning_step=None)
    state, due = _run(just_graduated, *ratings)
    assert state.interval_days == interval
    assert state.ease == pytest.approx(ease)
    assert due == NOW + timedelta(days=interval)


def test_forgetting_a_learned_card_is_a_lapse_and_relearns_it():
    learned = ReviewState(ease=2.5, interval_days=15, repetitions=3, learning_step=None)
    state, due = _run(learned, "again")
    assert state.lapses == 1
    assert state.ease == pytest.approx(2.3)
    assert (state.learning_step, state.repetitions) == (0, 0)
    assert due == NOW + RELEARN_DELAY

    state, due = _run(state, "good")
    assert state.learning_step is None
    assert (state.interval_days, state.repetitions, state.lapses) == (1, 1, 1)
    assert due == NOW + timedelta(days=1)


def test_again_while_relearning_costs_no_more_ease():
    relearning = ReviewState(ease=2.3, lapses=1, learning_step=0)
    state, due = _run(relearning, "again")
    assert state.ease == pytest.approx(2.3)
    assert state.lapses == 1
    assert due == NOW + RELEARN_DELAY


def test_ease_never_drops_below_minimum():
    state = ReviewState(ease=MIN_EASE, interval_days=5, repetitions=3, learning_step=None)
    assert review(state, "again", NOW).state.ease == MIN_EASE
    assert review(state, "hard", NOW).state.ease == MIN_EASE


def test_long_intervals_always_grow():
    state = ReviewState(ease=MIN_EASE, interval_days=1, repetitions=5, learning_step=None)
    assert review(state, "hard", NOW).state.interval_days == 2


def test_graduated_default_is_distinct_from_new():
    assert ReviewState().learning_step == 0
    assert GRADUATED.learning_step is None
