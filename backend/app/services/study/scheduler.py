"""Spaced-repetition scheduling with four answer buttons (Task 9.4).

SM-2 for learned cards, with Anki-style learning steps in front of it:

- A new card goes through short learning steps (1 minute, then 10 minutes)
  before it graduates to a 1-day interval. Easy graduates it straight to
  4 days. Ease is not touched while learning: missing a card you have only
  just met says nothing about how hard it will be to remember.
- A learned card answered Again is a lapse: ease drops by 0.2 and it is
  relearned through one 10-minute step, then restarts at 1 day.
- Otherwise the usual SM-2 intervals and ease adjustments apply.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal

Rating = Literal["again", "hard", "good", "easy"]

MIN_EASE = 1.3
DEFAULT_EASE = 2.5
LAPSE_EASE_PENALTY = 0.2
LEARNING_STEPS = (timedelta(minutes=1), timedelta(minutes=10))
RELEARNING_STEPS = (timedelta(minutes=10),)
RELEARN_DELAY = RELEARNING_STEPS[0]
GRADUATING_INTERVAL_DAYS = 1
EASY_INTERVAL_DAYS = 4

# SM-2 answer quality for each button.
_QUALITY: dict[str, int] = {"hard": 3, "good": 4, "easy": 5}
_SECOND_INTERVAL: dict[str, int] = {"hard": 3, "good": 6, "easy": 8}


@dataclass(frozen=True)
class ReviewState:
    ease: float = DEFAULT_EASE
    interval_days: int = 0
    repetitions: int = 0
    lapses: int = 0
    #: Index into the (re)learning steps, or None once the card has graduated.
    learning_step: int | None = 0


@dataclass(frozen=True)
class ReviewOutcome:
    state: ReviewState
    due_at: datetime


def _updated_ease(ease: float, quality: int) -> float:
    miss = 5 - quality
    return max(MIN_EASE, round(ease + 0.1 - miss * (0.08 + miss * 0.02), 4))


def review(state: ReviewState, rating: Rating, now: datetime) -> ReviewOutcome:
    """Apply one review and return the card's new state and due time."""
    if state.learning_step is not None:
        return _learning_review(state, rating, now)

    if rating == "again":
        lapsed = ReviewState(
            ease=max(MIN_EASE, round(state.ease - LAPSE_EASE_PENALTY, 4)),
            interval_days=0,
            repetitions=0,
            lapses=state.lapses + 1,
            learning_step=0,
        )
        return ReviewOutcome(lapsed, now + RELEARNING_STEPS[0])

    repetitions = state.repetitions + 1
    if repetitions == 1:
        interval = EASY_INTERVAL_DAYS if rating == "easy" else GRADUATING_INTERVAL_DAYS
    elif repetitions == 2:
        interval = _SECOND_INTERVAL[rating]
    else:
        factor = {"hard": 1.2, "good": state.ease, "easy": state.ease * 1.3}[rating]
        interval = max(state.interval_days + 1, round(state.interval_days * factor))

    updated = replace(
        state,
        ease=_updated_ease(state.ease, _QUALITY[rating]),
        interval_days=interval,
        repetitions=repetitions,
    )
    return ReviewOutcome(updated, now + timedelta(days=interval))


def _learning_review(state: ReviewState, rating: Rating, now: datetime) -> ReviewOutcome:
    # A card that has lapsed is relearning; one that never graduated is learning.
    steps = RELEARNING_STEPS if state.lapses else LEARNING_STEPS
    step = min(state.learning_step or 0, len(steps) - 1)

    if rating == "again":
        return ReviewOutcome(replace(state, learning_step=0), now + steps[0])
    if rating == "hard":
        return ReviewOutcome(replace(state, learning_step=step), now + steps[step])
    if rating == "good" and step + 1 < len(steps):
        return ReviewOutcome(replace(state, learning_step=step + 1), now + steps[step + 1])

    interval = EASY_INTERVAL_DAYS if rating == "easy" else GRADUATING_INTERVAL_DAYS
    graduated = replace(state, interval_days=interval, repetitions=1, learning_step=None)
    return ReviewOutcome(graduated, now + timedelta(days=interval))
