"""LLM flashcard and quiz generation, and short-answer grading (Task 9.5).

Pages are packed into batches that fit the model's context window. Output is
parsed from tagged blocks (providers only return text) and every item must
name one of the pages it was given, so nothing uncited survives.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from app.errors import ErrorCode, HypatiaError, LLMProviderError
from app.models.db_models import CardType, QuestionType
from app.services.llm_service import get_llm_provider
from app.services.prompts.flashcard_prompt import FLASHCARD_SYSTEM_PROMPT
from app.services.prompts.grading_prompt import GRADING_SYSTEM_PROMPT
from app.services.prompts.quiz_prompt import QUIZ_SYSTEM_PROMPT
from app.services.study.extractors import CardCandidate, PageDoc, normalize_text, slug_for_path
from app.services.study.quiz_builder import BLANK, QuestionDraft
from app.services.wiki_engine import (
    _count_tokens,
    _output_budget,
    _prompt_budget,
    _truncate_to_tokens,
)
from app.utils.logging import get_logger

logger = get_logger()

_T = TypeVar("_T")
Progress = Callable[[int, int], None]
IsCancelled = Callable[[], bool]

_LLM_ERRORS = (OSError, ValueError, RuntimeError, TimeoutError, HypatiaError)

_CARD_RE = re.compile(r"<card\b([^>]*)>(.*?)</card>", re.DOTALL | re.IGNORECASE)
_QUESTION_RE = re.compile(r"<question\b([^>]*)>(.*?)</question>", re.DOTALL | re.IGNORECASE)
_CHOICE_RE = re.compile(r"<choice\b([^>]*)>(.*?)</choice>", re.DOTALL | re.IGNORECASE)
_PAIR_RE = re.compile(r"<pair>(.*?)</pair>", re.DOTALL | re.IGNORECASE)
_ATTR_RE = re.compile(r'([\w-]+)\s*=\s*"([^"]*)"')
_CLOZE_TERM_RE = re.compile(r"\{\{c1::(.+?)(?:::[^}]*)?\}\}")
_BLANK_RE = re.compile(r"_{3,}")
_SCORE_RE = re.compile(r"<score>\s*([0-9]*\.?[0-9]+)\s*</score>", re.IGNORECASE)

_MAX_FIELD_CHARS = 4000
_MAX_ANSWER_CHARS = 4000
_INSTRUCTION_RESERVE = 200
_DRAFT_SHARE = 0.25
_MIN_PAGE_BUDGET = 256
_GRADING_MAX_TOKENS = 512
_CORRECT_THRESHOLD = 0.7

_QUESTION_TYPE_ALIASES = {
    "mcq": QuestionType.MCQ,
    "multiple-choice": QuestionType.MCQ,
    "tf": QuestionType.TRUE_FALSE,
    "true-false": QuestionType.TRUE_FALSE,
    "truefalse": QuestionType.TRUE_FALSE,
    "fill": QuestionType.FILL,
    "matching": QuestionType.MATCHING,
    "short": QuestionType.SHORT,
}


class GenerationCancelled(Exception):
    """The user cancelled the generation task between batches."""


@dataclass(frozen=True)
class AIGrade:
    score: float
    feedback: str

    @property
    def correct(self) -> bool:
        return self.score >= _CORRECT_THRESHOLD


def _attrs(raw: str) -> dict[str, str]:
    return {k.lower(): v for k, v in _ATTR_RE.findall(raw)}


def _tag(body: str, name: str) -> str:
    match = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", body, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _fits(text: str) -> bool:
    return bool(text) and len(text) <= _MAX_FIELD_CHARS


def page_block(doc: PageDoc) -> str:
    return f"## Page: {doc.path}\nTitle: {doc.title}\n\n{doc.body.strip()}"


def batch_pages(docs: Sequence[PageDoc], budget: int) -> list[list[tuple[PageDoc, str]]]:
    """Pack page blocks into batches of at most ``budget`` tokens; oversize pages are cut."""
    batches: list[list[tuple[PageDoc, str]]] = []
    current: list[tuple[PageDoc, str]] = []
    used = 0
    for doc in docs:
        block = page_block(doc)
        tokens = _count_tokens(block)
        if tokens > budget:
            block = _truncate_to_tokens(block, budget)
            tokens = budget
        if current and used + tokens > budget:
            batches.append(current)
            current, used = [], 0
        current.append((doc, block))
        used += tokens
    if current:
        batches.append(current)
    return batches


def _page_budget(system_prompt: str, with_drafts: bool) -> int:
    available = _prompt_budget() - _count_tokens(system_prompt) - _INSTRUCTION_RESERVE
    if with_drafts:
        available = int(available * (1 - _DRAFT_SHARE))
    return max(available, _MIN_PAGE_BUDGET)


def _draft_budget(system_prompt: str) -> int:
    available = _prompt_budget() - _count_tokens(system_prompt) - _INSTRUCTION_RESERVE
    return max(int(available * _DRAFT_SHARE), 0)


def _page_resolver(docs: Iterable[PageDoc]) -> Callable[[str], PageDoc | None]:
    """Match the LLM's ``page`` attribute by exact path, slug, or title."""
    index: dict[str, PageDoc] = {}
    for doc in docs:
        index.setdefault(normalize_text(doc.title), doc)
        index.setdefault(slug_for_path(doc.path), doc)
        index[doc.path.lower()] = doc

    def resolve(ref: str) -> PageDoc | None:
        ref = ref.strip()
        if not ref:
            return None
        return (
            index.get(ref.lower())
            or index.get(slug_for_path(ref))
            or index.get(normalize_text(ref))
        )

    return resolve


def parse_cards(
    raw: str, docs: Sequence[PageDoc], card_types: Iterable[CardType]
) -> list[CardCandidate]:
    allowed = set(card_types)
    resolve = _page_resolver(docs)
    cards: list[CardCandidate] = []
    for attr_text, body in _CARD_RE.findall(raw):
        attrs = _attrs(attr_text)
        doc = resolve(attrs.get("page", ""))
        if doc is None:
            continue
        card_type = CardType.CLOZE if attrs.get("type", "").lower() == "cloze" else CardType.BASIC
        if card_type not in allowed:
            continue
        front = _tag(body, "front")
        if not _fits(front):
            continue
        if card_type == CardType.CLOZE:
            term = _CLOZE_TERM_RE.search(front)
            if term is None:
                continue
            back = term.group(1).strip()
        else:
            back = _tag(body, "back")
            if not _fits(back):
                continue
        cards.append(
            CardCandidate(
                front=front,
                back=back,
                card_type=card_type,
                page_path=doc.path,
                source_file_ids=list(doc.source_file_ids),
                tags=list(doc.tags),
                score=1.0,
                label=front,
            )
        )
    return cards


def _mcq(body: str, rng: random.Random) -> tuple[dict, dict] | None:
    choices = [(_attrs(a), text.strip()) for a, text in _CHOICE_RE.findall(body)]
    if not 3 <= len(choices) <= 6:
        return None
    texts = [text for _, text in choices]
    if not all(_fits(t) for t in texts) or len({normalize_text(t) for t in texts}) != len(texts):
        return None
    correct = [i for i, (attrs, _) in enumerate(choices) if attrs.get("correct") == "true"]
    if len(correct) != 1:
        return None
    order = list(range(len(texts)))
    rng.shuffle(order)
    return {"options": [texts[i] for i in order]}, {"choice": order.index(correct[0])}


def _matching(body: str, rng: random.Random) -> tuple[dict, dict] | None:
    pairs = [(_tag(p, "term"), _tag(p, "definition")) for p in _PAIR_RE.findall(body)]
    pairs = [(t, d) for t, d in pairs if _fits(t) and _fits(d)]
    if not 3 <= len(pairs) <= 6 or len({normalize_text(t) for t, _ in pairs}) != len(pairs):
        return None
    order = list(range(len(pairs)))
    rng.shuffle(order)
    choices = {"left": [t for t, _ in pairs], "right": [pairs[i][1] for i in order]}
    return choices, {"pairs": [order.index(i) for i in range(len(pairs))]}


def parse_questions(
    raw: str,
    docs: Sequence[PageDoc],
    question_types: Iterable[QuestionType],
    rng: random.Random,
) -> list[QuestionDraft]:
    allowed = set(question_types)
    resolve = _page_resolver(docs)
    drafts: list[QuestionDraft] = []
    for attr_text, body in _QUESTION_RE.findall(raw):
        attrs = _attrs(attr_text)
        doc = resolve(attrs.get("page", ""))
        qtype = _QUESTION_TYPE_ALIASES.get(attrs.get("type", "").lower())
        if doc is None or qtype is None or qtype not in allowed:
            continue
        prompt = _tag(body, "prompt")
        answer = _tag(body, "answer")
        choices: dict | None = None
        answer_json: dict

        if qtype == QuestionType.MATCHING:
            built = _matching(body, rng)
            if built is None:
                continue
            choices, answer_json = built
            prompt = prompt or "Match each term to its description."
        elif not _fits(prompt):
            continue
        elif qtype == QuestionType.MCQ:
            built = _mcq(body, rng)
            if built is None:
                continue
            choices, answer_json = built
        elif qtype == QuestionType.TRUE_FALSE:
            if answer.lower() not in ("true", "false"):
                continue
            answer_json = {"value": answer.lower() == "true"}
            prompt = f"**True or false?**\n\n> {prompt}"
        elif qtype == QuestionType.FILL:
            accepted = [a.strip() for a in answer.split("|") if a.strip()]
            prompt = _CLOZE_TERM_RE.sub(BLANK, prompt)
            if not accepted or not _BLANK_RE.search(prompt):
                continue
            answer_json = {"accepted": accepted}
            prompt = f"Fill in the blank:\n\n{_BLANK_RE.sub(BLANK, prompt)}"
        else:
            if not _fits(answer):
                continue
            answer_json = {"reference": answer, "rubric": _tag(body, "rubric") or None}

        drafts.append(
            QuestionDraft(
                question_type=qtype,
                prompt=prompt,
                answer=answer_json,
                choices=choices,
                explanation=_tag(body, "explanation") or None,
                page_paths=[doc.path],
                source_file_ids=list(doc.source_file_ids),
            )
        )
    return drafts


def _share(count: int, tokens: int, total_tokens: int) -> int:
    return max(1, math.ceil(count * tokens / max(total_tokens, 1)))


def _round_robin(items: list[_T], key: Callable[[_T], object], limit: int) -> list[_T]:
    """Interleave items across groups (pages or question types) so no group dominates."""
    groups: dict[object, list[_T]] = {}
    for item in items:
        groups.setdefault(key(item), []).append(item)
    ordered: list[_T] = []
    queues = list(groups.values())
    depth = 0
    while len(ordered) < limit and any(depth < len(q) for q in queues):
        for queue in queues:
            if depth < len(queue) and len(ordered) < limit:
                ordered.append(queue[depth])
        depth += 1
    return ordered


def _wrap_error(error: BaseException) -> HypatiaError:
    if isinstance(error, HypatiaError):
        return error
    return LLMProviderError(ErrorCode.LLM_UNAVAILABLE, detail=f"LLM error: {error}")


async def _run_batches(
    system_prompt: str,
    prompts: list[str],
    handle: Callable[[int, str], None],
    progress: Progress | None,
    cancelled: IsCancelled | None,
) -> None:
    """Send each prompt; a failed batch is skipped unless every batch fails."""
    provider = get_llm_provider()
    failures: list[BaseException] = []
    try:
        for index, prompt in enumerate(prompts):
            if cancelled is not None and cancelled():
                raise GenerationCancelled
            if progress is not None:
                progress(index, len(prompts))
            try:
                raw = await provider.complete(system_prompt, prompt, max_tokens=_output_budget())
            except _LLM_ERRORS as e:
                logger.warning("study_llm_batch_failed", batch=index, error=str(e))
                failures.append(e)
                continue
            handle(index, raw)
    finally:
        await provider.close()
    if prompts and len(failures) == len(prompts):
        raise _wrap_error(failures[-1])


def _drafts_block(lines: list[str], budget: int) -> str:
    text = "\n".join(lines)
    return _truncate_to_tokens(text, budget) if text else ""


def _render_draft_card(card: CardCandidate) -> str:
    if card.card_type == CardType.CLOZE:
        return f'<card type="cloze" page="{card.page_path}">\n<front>{card.front}</front>\n</card>'
    return (
        f'<card type="basic" page="{card.page_path}">\n'
        f"<front>{card.front}</front>\n<back>{card.back}</back>\n</card>"
    )


async def generate_cards_with_llm(
    docs: Sequence[PageDoc],
    *,
    count: int,
    card_types: Sequence[CardType],
    drafts: Sequence[CardCandidate] = (),
    progress: Progress | None = None,
    cancelled: IsCancelled | None = None,
) -> list[CardCandidate]:
    batches = batch_pages(docs, _page_budget(FLASHCARD_SYSTEM_PROMPT, bool(drafts)))
    sizes = [sum(_count_tokens(block) for _, block in batch) for batch in batches]
    type_names = ", ".join(t.value for t in card_types)
    draft_budget = _draft_budget(FLASHCARD_SYSTEM_PROMPT)

    prompts: list[str] = []
    for batch, size in zip(batches, sizes, strict=True):
        paths = {doc.path for doc, _ in batch}
        draft_text = _drafts_block(
            [_render_draft_card(d) for d in drafts if d.page_path in paths], draft_budget
        )
        parts = [
            (
                f"## Request\n\nWrite up to {_share(count, size, sum(sizes))} flashcards. "
                f"Allowed types: {type_names}."
            )
        ]
        if draft_text:
            parts.append(f"## Draft cards\n\n{draft_text}")
        parts.append("## Wiki pages\n\n" + "\n\n---\n\n".join(block for _, block in batch))
        prompts.append("\n\n".join(parts))

    seen: set[str] = set()
    cards: list[CardCandidate] = []

    def handle(index: int, raw: str) -> None:
        for card in parse_cards(raw, [doc for doc, _ in batches[index]], card_types):
            key = normalize_text(card.front)
            if key not in seen:
                seen.add(key)
                cards.append(card)

    await _run_batches(FLASHCARD_SYSTEM_PROMPT, prompts, handle, progress, cancelled)
    return _round_robin(cards, lambda c: c.page_path, count)


async def generate_questions_with_llm(
    docs: Sequence[PageDoc],
    *,
    count: int,
    question_types: Sequence[QuestionType],
    seed: int,
    key_facts: Sequence[CardCandidate] = (),
    progress: Progress | None = None,
    cancelled: IsCancelled | None = None,
) -> list[QuestionDraft]:
    rng = random.Random(seed)
    batches = batch_pages(docs, _page_budget(QUIZ_SYSTEM_PROMPT, bool(key_facts)))
    sizes = [sum(_count_tokens(block) for _, block in batch) for batch in batches]
    type_names = ", ".join(t.value for t in question_types)
    fact_budget = _draft_budget(QUIZ_SYSTEM_PROMPT)

    prompts: list[str] = []
    for batch, size in zip(batches, sizes, strict=True):
        paths = {doc.path for doc, _ in batch}
        facts = _drafts_block(
            [
                f"- ({fact.page_path}) {fact.front} \u2014 {fact.back}"
                for fact in key_facts
                if fact.page_path in paths and fact.card_type == CardType.BASIC
            ],
            fact_budget,
        )
        parts = [
            (
                f"## Request\n\nWrite up to {_share(count, size, sum(sizes))} questions. "
                f"Allowed types: {type_names}."
            )
        ]
        if facts:
            parts.append(f"## Key facts\n\n{facts}")
        parts.append("## Wiki pages\n\n" + "\n\n---\n\n".join(block for _, block in batch))
        prompts.append("\n\n".join(parts))

    seen: set[str] = set()
    questions: list[QuestionDraft] = []

    def handle(index: int, raw: str) -> None:
        batch_docs = [doc for doc, _ in batches[index]]
        for question in parse_questions(raw, batch_docs, question_types, rng):
            key = normalize_text(question.prompt + str(question.choices))
            if key not in seen:
                seen.add(key)
                questions.append(question)

    await _run_batches(QUIZ_SYSTEM_PROMPT, prompts, handle, progress, cancelled)
    return _round_robin(questions, lambda q: q.question_type, count)


async def grade_short_answer(
    prompt: str, reference: str, rubric: str | None, answer: str
) -> AIGrade | None:
    """Score a typed answer from 0 to 1, or None when the LLM is unavailable or unclear."""
    user_prompt = (
        f"## Question\n\n{prompt}\n\n## Model answer\n\n{reference}\n\n"
        f"## Rubric\n\n{rubric or '(none: compare with the model answer)'}\n\n"
        f"## Student answer\n\n<student_answer>\n{answer[:_MAX_ANSWER_CHARS]}\n</student_answer>"
    )
    provider = get_llm_provider()
    try:
        raw = await provider.complete(
            GRADING_SYSTEM_PROMPT,
            user_prompt,
            max_tokens=min(_GRADING_MAX_TOKENS, _output_budget()),
        )
    except _LLM_ERRORS as e:
        logger.warning("study_grading_failed", error=str(e))
        return None
    finally:
        await provider.close()

    match = _SCORE_RE.search(raw)
    if match is None:
        logger.warning("study_grading_unparseable", output_length=len(raw))
        return None
    score = float(match.group(1))
    if 1 < score <= 100:
        score /= 100
    return AIGrade(score=min(max(score, 0.0), 1.0), feedback=_tag(raw, "feedback"))
