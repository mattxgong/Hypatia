"""SM-2 spaced-repetition scheduling with four answer buttons (Task 9.4)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal

Rating = Literal["again", "hard", "good", "easy"]

MIN_EASE = 1.3
DEFAULT_EASE = 2.5
RELEARN_DELAY = timedelta(minutes=10)

# SM-2 answer quality for each button.
_QUALITY: dict[str, int] = {"hard": 3, "good": 4, "easy": 5}
_SECOND_INTERVAL: dict[str, int] = {"hard": 3, "good": 6, "easy": 8}


@dataclass(frozen=True)
class ReviewState:
    ease: float = DEFAULT_EASE
    interval_days: int = 0
    repetitions: int = 0
    lapses: int = 0


@dataclass(frozen=True)
class ReviewOutcome:
    state: ReviewState
    due_at: datetime


def _updated_ease(ease: float, quality: int) -> float:
    miss = 5 - quality
    return max(MIN_EASE, round(ease + 0.1 - miss * (0.08 + miss * 0.02), 4))


def review(state: ReviewState, rating: Rating, now: datetime) -> ReviewOutcome:
    """Apply one review. ``again`` resets the card and shows it again shortly."""
    if rating == "again":
        lapsed = ReviewState(
            ease=max(MIN_EASE, round(state.ease - 0.2, 4)),
            interval_days=0,
            repetitions=0,
            lapses=state.lapses + (1 if state.repetitions > 0 else 0),
        )
        return ReviewOutcome(lapsed, now + RELEARN_DELAY)

    repetitions = state.repetitions + 1
    if repetitions == 1:
        interval = 4 if rating == "easy" else 1
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
