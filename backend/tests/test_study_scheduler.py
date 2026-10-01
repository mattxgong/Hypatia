"""SM-2 scheduling (Task 9.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.study.scheduler import MIN_EASE, RELEARN_DELAY, ReviewState, review

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("ratings", "interval", "ease"),
    [
        (["good"], 1, 2.5),
        (["easy"], 4, 2.6),
        (["hard"], 1, 2.36),
        (["good", "good"], 6, 2.5),
        (["good", "hard"], 3, 2.36),
        (["good", "easy"], 8, 2.6),
        (["good", "good", "good"], 15, 2.5),
        (["good", "good", "hard"], 7, 2.36),
        (["good", "good", "easy"], 20, 2.6),
    ],
)
def test_interval_and_ease_progression(ratings: list[str], interval: int, ease: float) -> None:
    state = ReviewState()
    for rating in ratings:
        outcome = review(state, rating, NOW)  # type: ignore[arg-type]
        state = outcome.state
    assert state.interval_days == interval
    assert state.ease == pytest.approx(ease)
    assert state.repetitions == len(ratings)
    assert outcome.due_at == NOW + timedelta(days=interval)


def test_again_resets_and_counts_a_lapse_for_learned_cards() -> None:
    learned = ReviewState(ease=2.5, interval_days=15, repetitions=3, lapses=0)
    outcome = review(learned, "again", NOW)
    assert outcome.state.repetitions == 0
    assert outcome.state.interval_days == 0
    assert outcome.state.lapses == 1
    assert outcome.state.ease == pytest.approx(2.3)
    assert outcome.due_at == NOW + RELEARN_DELAY


def test_again_on_a_new_card_is_not_a_lapse() -> None:
    assert review(ReviewState(), "again", NOW).state.lapses == 0


def test_ease_never_drops_below_minimum() -> None:
    state = ReviewState(ease=MIN_EASE)
    assert review(state, "again", NOW).state.ease == MIN_EASE
    assert review(state, "hard", NOW).state.ease == MIN_EASE


def test_long_intervals_always_grow() -> None:
    state = ReviewState(ease=MIN_EASE, interval_days=1, repetitions=5)
    assert review(state, "hard", NOW).state.interval_days == 2
