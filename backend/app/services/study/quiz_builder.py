"""Assemble practice-quiz questions from heuristic flashcards (Task 9.3)."""

from __future__ import annotations

import random
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.models.db_models import CardType, QuestionType
from app.services.study.extractors import (
    CardCandidate,
    normalize_text,
    term_pattern,
)

HEURISTIC_QUESTION_TYPES = (
    QuestionType.MCQ,
    QuestionType.TRUE_FALSE,
    QuestionType.MATCHING,
    QuestionType.FILL,
)

BLANK = "_____"
_MCQ_CHOICES = 4
_MATCHING_PAIRS = 4
_MAX_MATCHING_BACK_CHARS = 250
_CLOZE_RE = re.compile(r"\{\{c\d+::(.+?)(?:::[^}]*)?\}\}")
# Keep math, code, and links intact when hiding a term.
_REDACT_SKIP_RE = re.compile(
    r"\$\$.+?\$\$|\\\[.+?\\\]|\\\(.+?\\\)|`[^`\n]+`|!?\[[^\]\n]*\]\([^)\n]*\)|\[\[[^\]]+\]\]",
    re.DOTALL,
)
_BLANK_ABBREVIATION_RE = re.compile(r"_____ \([A-Z][A-Za-z]{1,7}\)")


def _link_mentions(link: str, pattern: re.Pattern[str]) -> bool:
    target, _, label = link[2:-2].partition("|")
    return bool(pattern.search(label) or pattern.search(target.replace("-", " ")))


@dataclass
class QuestionDraft:
    question_type: QuestionType
    prompt: str
    answer: dict
    choices: dict | None = None
    explanation: str | None = None
    page_paths: list[str] = field(default_factory=list)
    source_file_ids: list[str] = field(default_factory=list)


def redact(text: str, subject: str | None) -> str:
    """Hide ``subject`` in ``text`` so a choice does not give away its own answer."""
    if not subject:
        return text
    pattern = term_pattern(subject)
    pieces: list[str] = []
    last = 0
    for skip in _REDACT_SKIP_RE.finditer(text):
        pieces.append(pattern.sub(BLANK, text[last : skip.start()]))
        span = skip.group(0)
        is_link = span.startswith("[[")
        pieces.append(BLANK if is_link and _link_mentions(span, pattern) else span)
        last = skip.end()
    pieces.append(pattern.sub(BLANK, text[last:]))
    return _BLANK_ABBREVIATION_RE.sub(BLANK, "".join(pieces))


def cloze_prompt(front: str) -> str:
    return _CLOZE_RE.sub(BLANK, front)


def cloze_reveal(front: str) -> str:
    return _CLOZE_RE.sub(lambda m: f"**{m.group(1)}**", front)


def _question_text(card: CardCandidate) -> str:
    return (
        card.front
        if card.front.rstrip().endswith("?")
        else f"Which description matches **{card.front}**?"
    )


def _tokens(text: str) -> set[str]:
    return {w for w in normalize_text(text).split() if len(w) > 3}


def _pick_distractors(
    card: CardCandidate,
    pool: list[CardCandidate],
    count: int,
    rng: random.Random,
) -> list[CardCandidate]:
    """Prefer backs from other pages that share tags and vocabulary with the answer."""
    answer_key = normalize_text(card.back)
    answer_tokens = _tokens(card.back)
    tags = set(card.tags)
    scored: list[tuple[float, CardCandidate]] = []
    for other in pool:
        if other is card or other.page_path == card.page_path:
            continue
        if normalize_text(other.back) == answer_key:
            continue
        other_tokens = _tokens(other.back)
        union = answer_tokens | other_tokens
        overlap = len(answer_tokens & other_tokens) / len(union) if union else 0.0
        length_gap = abs(len(other.back) - len(card.back)) / max(len(card.back), len(other.back))
        score = 2 * len(tags & set(other.tags)) + overlap - 0.5 * length_gap + rng.random() * 0.1
        scored.append((score, other))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    picked: list[CardCandidate] = []
    seen = {answer_key}
    for _, other in scored:
        key = normalize_text(other.back)
        if key not in seen:
            seen.add(key)
            picked.append(other)
            if len(picked) == count:
                break
    return picked


def _sources(cards: Iterable[CardCandidate]) -> tuple[list[str], list[str]]:
    paths = list(dict.fromkeys(c.page_path for c in cards))
    files = list(dict.fromkeys(f for c in cards for f in c.source_file_ids))
    return paths, files


def _mcq(
    card: CardCandidate, pool: list[CardCandidate], rng: random.Random
) -> QuestionDraft | None:
    distractors = _pick_distractors(card, pool, _MCQ_CHOICES - 1, rng)
    if len(distractors) < _MCQ_CHOICES - 1:
        return None
    options = [redact(card.back, card.subject)] + [redact(d.back, d.subject) for d in distractors]
    order = list(range(len(options)))
    rng.shuffle(order)
    paths, files = _sources([card])
    return QuestionDraft(
        question_type=QuestionType.MCQ,
        prompt=_question_text(card),
        choices={"options": [options[i] for i in order]},
        answer={"choice": order.index(0)},
        explanation=card.back,
        page_paths=paths,
        source_file_ids=files,
    )


def _true_false(
    card: CardCandidate, pool: list[CardCandidate], rng: random.Random
) -> QuestionDraft | None:
    is_true = rng.random() < 0.5
    if is_true:
        statement = redact(card.back, card.subject)
    else:
        distractors = _pick_distractors(card, pool, 1, rng)
        if not distractors:
            return None
        statement = redact(distractors[0].back, distractors[0].subject)
    paths, files = _sources([card])
    if card.front.rstrip().endswith("?"):
        lead = f"The statement below correctly answers: {card.front}"
    else:
        lead = f"The statement below describes **{card.front}**."
    return QuestionDraft(
        question_type=QuestionType.TRUE_FALSE,
        prompt=f"**True or false?** {lead}\n\n> {statement}",
        answer={"value": is_true},
        explanation=card.back,
        page_paths=paths,
        source_file_ids=files,
    )


def _matching(cards: list[CardCandidate], rng: random.Random) -> QuestionDraft:
    right = [redact(c.back, c.subject) for c in cards]
    order = list(range(len(cards)))
    rng.shuffle(order)
    paths, files = _sources(cards)
    return QuestionDraft(
        question_type=QuestionType.MATCHING,
        prompt="Match each term to its description.",
        choices={"left": [c.label or c.front for c in cards], "right": [right[i] for i in order]},
        answer={"pairs": [order.index(i) for i in range(len(cards))]},
        explanation="\n\n".join(f"**{c.label or c.front}**: {c.back}" for c in cards),
        page_paths=paths,
        source_file_ids=files,
    )


def _fill(card: CardCandidate) -> QuestionDraft:
    paths, files = _sources([card])
    return QuestionDraft(
        question_type=QuestionType.FILL,
        prompt=f"Fill in the blank:\n\n{cloze_prompt(card.front)}",
        answer={"accepted": [card.back]},
        explanation=cloze_reveal(card.front),
        page_paths=paths,
        source_file_ids=files,
    )


def build_quiz(
    cards: list[CardCandidate],
    *,
    question_types: Iterable[QuestionType],
    count: int,
    seed: int,
) -> list[QuestionDraft]:
    """Build up to ``count`` questions, cycling through the requested types.

    A type drops out of the rotation once the card pool can no longer supply it.
    """
    rng = random.Random(seed)
    basic = [c for c in cards if c.card_type == CardType.BASIC]
    cloze = [c for c in cards if c.card_type == CardType.CLOZE]
    rng.shuffle(basic)
    rng.shuffle(cloze)
    used: set[int] = set()
    rotation = [t for t in dict.fromkeys(question_types) if t in HEURISTIC_QUESTION_TYPES]
    questions: list[QuestionDraft] = []

    def next_unused(source: list[CardCandidate]) -> CardCandidate | None:
        return next((c for c in source if id(c) not in used), None)

    while rotation and len(questions) < count:
        for qtype in list(rotation):
            if len(questions) >= count:
                break
            draft: QuestionDraft | None = None
            if qtype == QuestionType.FILL:
                card = next_unused(cloze)
                if card is not None:
                    used.add(id(card))
                    draft = _fill(card)
            elif qtype == QuestionType.MATCHING:
                group: list[CardCandidate] = []
                labels: set[str] = set()
                for c in basic:
                    label = normalize_text(c.label or c.front)
                    if id(c) in used or len(c.back) > _MAX_MATCHING_BACK_CHARS or label in labels:
                        continue
                    group.append(c)
                    labels.add(label)
                    if len(group) == _MATCHING_PAIRS:
                        break
                if len(group) == _MATCHING_PAIRS:
                    used.update(id(c) for c in group)
                    draft = _matching(group, rng)
            else:
                builder = _mcq if qtype == QuestionType.MCQ else _true_false
                for card in basic:
                    if id(card) in used:
                        continue
                    draft = builder(card, basic, rng)
                    if draft is not None:
                        used.add(id(card))
                        break
            if draft is None:
                rotation.remove(qtype)
            else:
                questions.append(draft)
    return questions
