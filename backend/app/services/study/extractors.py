"""Heuristic (no-LLM) flashcard extraction from wiki pages (Task 9.2).

Works on the markdown the wiki engine already wrote: page leads, section
leads, definition sentences, two-column tables, and cloze deletions of key
terms. Inline math, code, and citation links are masked before sentence
splitting so they are never cut in half or clozed.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

import yaml

from app.models.db_models import CardType

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---[ \t]*(?:\n|$)", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_BOLD_RE = re.compile(r"\*\*([^*\n]{3,60})\*\*")
_PROTECTED_RE = re.compile(
    r"\$\$.+?\$\$"
    r"|\\\[.+?\\\]"
    r"|\\\(.+?\\\)"
    r"|(?<![\\$])\$[^$\n]+\$"
    r"|`[^`\n]+`"
    r"|!?\[[^\]\n]*\]\([^)\n]*\)",
    re.DOTALL,
)
_PLACEHOLDER_RE = re.compile(r"\x00(\d+)\x00")
_SENTENCE_END_RE = re.compile(r"[.!?](?:\x00\d+\x00)*(?=\s+[A-Z0-9\x00\"'(\[]|\s*$)")
_BOLD_DEF_RE = re.compile(
    r"^\*\*(?P<term>[^*\n]{2,80}?)\*\*\s*"
    r"(?P<sep>:|\u2014|\u2013|-|is\b|are\b|refers to\b|means\b)\s*(?P<rest>.+)$",
    re.IGNORECASE,
)
_SENTENCE_DEF_RE = re.compile(
    r"^(?:(?:a|an|the)\s+)?(?P<term>[^\x00.,;:]{2,60}?)\s+(?:\([^)]{1,20}\)\s+)?"
    r"(?P<verb>is|are|refers to|means|denotes)\s+(?:defined as\s+)?(?:an?|the)\s+\S",
    re.IGNORECASE,
)
_NAVIGATION_SENTENCE_RE = re.compile(r"^(?:see\b|related\b|for more\b)", re.IGNORECASE)
_TABLE_SEPARATOR_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?$")

_CARD_CATEGORIES = {"concept", "entity", "synthesis"}
_SKIPPED_CATEGORIES = {"index", "log"}
_LEAD_HEADINGS = {"definition", "overview", "summary", "introduction", "description", "about"}
_SKIP_HEADINGS = {
    "sources",
    "references",
    "citations",
    "links",
    "open questions",
    "contradictions",
    "further reading",
}
_SKIP_HEADING_PREFIXES = ("related", "see also")

_MAX_BACK_SENTENCES = 3
_MAX_BACK_CHARS = 600
_MIN_BACK_CHARS = 30
_MIN_CLOZE_CHARS = 40
_MAX_CLOZE_CHARS = 300
_MAX_CLOZE_PER_PAGE = 3
_MAX_TABLE_CELL_CHARS = 300

_LEAD_SCORE = 1.0
_BOLD_DEF_SCORE = 0.9
_SENTENCE_DEF_SCORE = 0.8
_TABLE_SCORE = 0.7
_SECTION_SCORE = 0.6
_CLOZE_SCORE = 0.5


@dataclass
class PageDoc:
    """A wiki page reduced to what the extractors need."""

    path: str
    title: str
    category: str
    body: str
    tags: list[str] = field(default_factory=list)
    source_file_ids: list[str] = field(default_factory=list)


@dataclass
class CardCandidate:
    front: str
    back: str
    card_type: CardType
    page_path: str
    source_file_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    score: float = 0.0
    # Short term used for matching questions.
    label: str = ""
    # Term to hide when this card's back is shown as a quiz choice.
    subject: str | None = None


@dataclass
class _Section:
    heading: str | None
    blocks: list[str] = field(default_factory=list)


def split_frontmatter(content: str) -> tuple[dict, str]:
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        meta = None
    return (meta if isinstance(meta, dict) else {}), content[match.end() :]


def body_hash(content: str) -> str:
    """Hash of a page body, ignoring frontmatter so date/source bumps don't count as changes."""
    _, body = split_frontmatter(content)
    return hashlib.sha256(body.strip().encode("utf-8")).hexdigest()[:16]


def parse_page(
    path: str,
    title: str,
    category: str,
    content: str,
    source_file_ids: list[str] | None = None,
) -> PageDoc:
    meta, body = split_frontmatter(content)
    raw_tags = meta.get("tags")
    tags = [str(t) for t in raw_tags] if isinstance(raw_tags, list) else []
    return PageDoc(
        path=path,
        title=title,
        category=category,
        body=body,
        tags=tags,
        source_file_ids=list(source_file_ids or []),
    )


def slug_for_path(path: str) -> str:
    return PurePosixPath(path).stem.lower()


def normalize_text(text: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", text.lower()).split())


def _singular(text: str) -> str:
    lowered = text.lower()
    if lowered.endswith("s") and not lowered.endswith(("ss", "us", "is")):
        return text[:-1]
    return text


def _is_plural(title: str) -> bool:
    return _singular(title.split()[-1]) != title.split()[-1] if title.split() else False


def _what_is(term: str) -> str:
    return f"What {'are' if _is_plural(term) else 'is'} {term}?"


def _mask(text: str) -> tuple[str, list[str]]:
    spans: list[str] = []

    def replace(match: re.Match[str]) -> str:
        spans.append(match.group(0))
        return f"\x00{len(spans) - 1}\x00"

    return _PROTECTED_RE.sub(replace, text), spans


def _unmask(text: str, spans: list[str]) -> str:
    return _PLACEHOLDER_RE.sub(lambda m: spans[int(m.group(1))], text)


def _split_sentences(masked: str) -> list[str]:
    sentences: list[str] = []
    start = 0
    for match in _SENTENCE_END_RE.finditer(masked):
        sentence = masked[start : match.end()].strip()
        if sentence:
            sentences.append(sentence)
        start = match.end()
    tail = masked[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def _ends_sentence(masked_sentence: str) -> bool:
    return _PLACEHOLDER_RE.sub("", masked_sentence).rstrip().endswith((".", "!", "?"))


def _sections(body: str) -> list[_Section]:
    sections = [_Section(None)]
    buffer: list[str] = []
    in_fence = False

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            sections[-1].blocks.append(text)
        buffer.clear()

    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            buffer.append(line)
            continue
        if in_fence:
            buffer.append(line)
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            flush()
            sections.append(_Section(heading.group(2).strip()))
        elif not stripped:
            flush()
        else:
            buffer.append(line)
    flush()
    return [s for s in sections if s.heading or s.blocks]


def _skip_section(heading: str | None) -> bool:
    if heading is None:
        return False
    key = normalize_text(heading)
    return key in _SKIP_HEADINGS or key.startswith(_SKIP_HEADING_PREFIXES)


def _is_prose(block: str) -> bool:
    stripped = block.lstrip()
    return bool(stripped) and not (
        stripped.startswith(("```", "~~~", "|", "\\[", "$$", "<", "![", ">"))
        or _LIST_RE.match(stripped)
    )


def _leading_sentences(block: str) -> str:
    text = " ".join(line.strip() for line in block.splitlines())
    masked, spans = _mask(text)
    picked: list[str] = []
    total = 0
    for sentence in _split_sentences(masked):
        if not _ends_sentence(sentence):
            break
        if picked and total + len(sentence) > _MAX_BACK_CHARS:
            break
        picked.append(sentence)
        total += len(sentence)
        if len(picked) >= _MAX_BACK_SENTENCES:
            break
    return _unmask(" ".join(picked), spans)


def _first_prose(section: _Section) -> str:
    for block in section.blocks:
        # A lowercase start means the paragraph continues text cut by display math.
        if _is_prose(block) and not block.lstrip()[0].islower():
            text = _leading_sentences(block)
            if len(text) >= _MIN_BACK_CHARS:
                return text
    return ""


def resolve_wiki_links(text: str, slug_titles: dict[str, str]) -> str:
    """Replace ``[[slug|label]]`` links with their display text."""

    def replace(match: re.Match[str]) -> str:
        if match.group(2):
            return match.group(2).strip()
        slug = slug_for_path(match.group(1).strip())
        return slug_titles.get(slug, slug.replace("-", " "))

    return _WIKI_LINK_RE.sub(replace, text)


def term_pattern(term: str) -> re.Pattern[str]:
    """Case-insensitive whole-phrase pattern that also accepts the singular/plural form."""
    variants = {term, _singular(term) if _singular(term) != term else f"{term}s"}
    alternation = "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True))
    return re.compile(rf"(?<![\w-])(?:{alternation})(?!\w)", re.IGNORECASE)


def _card(
    doc: PageDoc,
    *,
    front: str,
    back: str,
    card_type: CardType,
    score: float,
    label: str,
    subject: str | None = None,
) -> CardCandidate:
    return CardCandidate(
        front=front,
        back=back,
        card_type=card_type,
        page_path=doc.path,
        source_file_ids=list(doc.source_file_ids),
        tags=list(doc.tags),
        score=score,
        label=label,
        subject=subject,
    )


def cards_from_page_lead(doc: PageDoc) -> list[CardCandidate]:
    if doc.category not in _CARD_CATEGORIES:
        return []
    sections = _sections(doc.body)
    lead = ""
    for section in sections:
        if section.heading and normalize_text(section.heading) in _LEAD_HEADINGS:
            lead = _first_prose(section)
            break
    if not lead:
        for section in sections:
            if _skip_section(section.heading):
                continue
            lead = _first_prose(section)
            if lead:
                break
    if not lead:
        return []

    if doc.category == "entity":
        front = f"Who or what is {doc.title}?"
    elif doc.category == "synthesis":
        front = f"Summarize: {doc.title}"
    else:
        front = _what_is(doc.title)
    return [
        _card(
            doc,
            front=front,
            back=lead,
            card_type=CardType.BASIC,
            score=_LEAD_SCORE,
            label=doc.title,
            subject=doc.title,
        )
    ]


def cards_from_sections(doc: PageDoc) -> list[CardCandidate]:
    if doc.category not in _CARD_CATEGORIES:
        return []
    cards: list[CardCandidate] = []
    title_key = normalize_text(doc.title)
    for section in _sections(doc.body):
        heading = section.heading
        if heading is None or _skip_section(heading):
            continue
        key = normalize_text(heading)
        if key in _LEAD_HEADINGS or key == title_key:
            continue
        back = _first_prose(section)
        if back:
            front = f"{doc.title}: {heading}"
            cards.append(
                _card(
                    doc,
                    front=front,
                    back=back,
                    card_type=CardType.BASIC,
                    score=_SECTION_SCORE,
                    label=front,
                    subject=doc.title,
                )
            )
    return cards


def cards_from_definitions(
    doc: PageDoc, known_terms: dict[str, str], slug_titles: dict[str, str]
) -> list[CardCandidate]:
    """Bold ``**Term**: definition`` lines, and "X is a ..." sentences about known terms.

    ``known_terms`` maps a normalized singular term to its display title.
    """
    if doc.category in _SKIPPED_CATEGORIES:
        return []
    cards: list[CardCandidate] = []
    for section in _sections(doc.body):
        if _skip_section(section.heading):
            continue
        for block in section.blocks:
            if not (_is_prose(block) or _LIST_RE.match(block.lstrip())):
                continue
            for line in block.splitlines():
                text = _LIST_RE.sub("", line.strip(), count=1)
                bold = _BOLD_DEF_RE.match(text)
                if bold:
                    term = bold.group("term").strip()
                    sep = bold.group("sep")
                    rest = bold.group("rest").strip()
                    if sep.isalpha() or " " in sep:
                        back = f"{term} {sep} {rest}"
                    else:
                        back = rest
                    if len(back) >= _MIN_BACK_CHARS // 2:
                        cards.append(
                            _card(
                                doc,
                                front=_what_is(term),
                                back=back,
                                card_type=CardType.BASIC,
                                score=_BOLD_DEF_SCORE,
                                label=term,
                                subject=term,
                            )
                        )
            if not _is_prose(block):
                continue
            joined = " ".join(line.strip() for line in block.splitlines())
            plain = resolve_wiki_links(joined.replace("**", ""), slug_titles)
            masked, spans = _mask(plain)
            for sentence in _split_sentences(masked):
                match = _SENTENCE_DEF_RE.match(sentence)
                if not match or not _ends_sentence(sentence):
                    continue
                title = known_terms.get(normalize_text(_singular(match.group("term").strip())))
                if title is None or normalize_text(title) == normalize_text(doc.title):
                    continue
                verb = "are" if match.group("verb").lower() == "are" else "is"
                cards.append(
                    _card(
                        doc,
                        front=f"What {verb} {title}?",
                        back=_unmask(sentence, spans),
                        card_type=CardType.BASIC,
                        score=_SENTENCE_DEF_SCORE,
                        label=title,
                        subject=title,
                    )
                )
    return cards


def _table_cells(line: str) -> list[str]:
    stripped = line.strip().removeprefix("|").removesuffix("|")
    return [cell.strip() for cell in stripped.split("|")]


def cards_from_tables(doc: PageDoc) -> list[CardCandidate]:
    if doc.category in _SKIPPED_CATEGORIES:
        return []
    cards: list[CardCandidate] = []
    for section in _sections(doc.body):
        for block in section.blocks:
            lines = block.splitlines()
            if len(lines) < 3 or not lines[0].lstrip().startswith("|"):
                continue
            if not _TABLE_SEPARATOR_RE.match(lines[1].strip()):
                continue
            header = _table_cells(lines[0])
            if len(header) != 2:
                continue
            for row in lines[2:]:
                cells = _table_cells(row)
                if len(cells) != 2 or not all(cells):
                    continue
                if any(len(c) > _MAX_TABLE_CELL_CHARS for c in cells):
                    continue
                front = f"{cells[0]} \u2014 {header[1]}" if header[1] else cells[0]
                cards.append(
                    _card(
                        doc,
                        front=front,
                        back=cells[1],
                        card_type=CardType.BASIC,
                        score=_TABLE_SCORE,
                        label=cells[0],
                    )
                )
    return cards


def term_weights(
    docs: list[PageDoc], terms: Iterable[str], slug_titles: dict[str, str]
) -> dict[str, float]:
    """IDF-style weight per normalized term: rarer terms across the pages score higher."""
    bodies = [resolve_wiki_links(d.body, slug_titles) for d in docs]
    total = len(bodies)
    weights: dict[str, float] = {}
    for term in terms:
        key = normalize_text(term)
        if not key or key in weights:
            continue
        pattern = term_pattern(term)
        df = sum(1 for body in bodies if pattern.search(body))
        weights[key] = math.log((1 + total) / (1 + df)) + 1
    return weights


def page_terms(doc: PageDoc, known_titles: Iterable[str]) -> set[str]:
    terms = {doc.title, *known_titles}
    terms.update(m.group(1).strip() for m in _BOLD_RE.finditer(doc.body))
    terms.update(m.group(2).strip() for m in _WIKI_LINK_RE.finditer(doc.body) if m.group(2))
    return {t for t in terms if len(t) >= 3}


def cloze_from_key_terms(
    doc: PageDoc,
    terms: Iterable[str],
    weights: dict[str, float],
    slug_titles: dict[str, str],
) -> list[CardCandidate]:
    if doc.category in _SKIPPED_CATEGORIES:
        return []
    patterns = [(t, term_pattern(t), weights.get(normalize_text(t), 1.0)) for t in terms]
    found: list[CardCandidate] = []
    for section in _sections(doc.body):
        if _skip_section(section.heading):
            continue
        for block in section.blocks:
            is_list = bool(_LIST_RE.match(block.lstrip()))
            if not (_is_prose(block) or is_list):
                continue
            lines = (
                block.splitlines()
                if is_list
                else [" ".join(line.strip() for line in block.splitlines())]
            )
            for line in lines:
                text = resolve_wiki_links(_LIST_RE.sub("", line.strip(), count=1), slug_titles)
                masked, spans = _mask(text.replace("**", ""))
                for sentence in _split_sentences(masked):
                    if not _MIN_CLOZE_CHARS <= len(sentence) <= _MAX_CLOZE_CHARS:
                        continue
                    if not _ends_sentence(sentence) or _NAVIGATION_SENTENCE_RE.match(sentence):
                        continue
                    best: tuple[float, int, re.Match[str]] | None = None
                    for term, pattern, weight in patterns:
                        matches = list(pattern.finditer(sentence))
                        if len(matches) != 1:
                            continue
                        rank = (weight, len(term))
                        if best is None or rank > best[:2]:
                            best = (weight, len(term), matches[0])
                    if best is None:
                        continue
                    weight, _, match = best
                    clozed = (
                        f"{sentence[: match.start()]}{{{{c1::{match.group(0)}}}}}"
                        f"{sentence[match.end() :]}"
                    )
                    found.append(
                        _card(
                            doc,
                            front=_unmask(clozed, spans),
                            back=match.group(0),
                            card_type=CardType.CLOZE,
                            score=_CLOZE_SCORE + 0.05 * min(weight, 4.0),
                            label=match.group(0),
                        )
                    )
    found.sort(key=lambda c: c.score, reverse=True)
    return found[:_MAX_CLOZE_PER_PAGE]


def generate_cards(
    docs: list[PageDoc],
    *,
    slug_titles: dict[str, str],
    card_types: Iterable[CardType] = (CardType.BASIC, CardType.CLOZE),
    limit: int | None = None,
) -> list[CardCandidate]:
    """Extract, dedupe, and interleave cards across pages, best cards first."""
    types = set(card_types)
    known_titles = list(dict.fromkeys(slug_titles.values()))
    known_terms = {normalize_text(_singular(t)): t for t in known_titles}
    all_terms = set(known_titles)
    for doc in docs:
        all_terms |= page_terms(doc, ())
    weights = term_weights(docs, all_terms, slug_titles) if CardType.CLOZE in types else {}

    candidates: list[CardCandidate] = []
    for doc in docs:
        if doc.category in _SKIPPED_CATEGORIES:
            continue
        if CardType.BASIC in types:
            candidates += cards_from_page_lead(doc)
            candidates += cards_from_definitions(doc, known_terms, slug_titles)
            candidates += cards_from_tables(doc)
            candidates += cards_from_sections(doc)
        if CardType.CLOZE in types:
            candidates += cloze_from_key_terms(
                doc, page_terms(doc, known_titles), weights, slug_titles
            )

    seen: set[str] = set()
    unique: list[CardCandidate] = []
    for card in sorted(candidates, key=lambda c: c.score, reverse=True):
        key = normalize_text(card.front)
        if key and key not in seen:
            seen.add(key)
            unique.append(card)

    by_page: dict[str, list[CardCandidate]] = {}
    for card in unique:
        by_page.setdefault(card.page_path, []).append(card)
    queues = [by_page[doc.path] for doc in docs if doc.path in by_page]

    ordered: list[CardCandidate] = []
    depth = 0
    while limit is None or len(ordered) < limit:
        added = False
        for queue in queues:
            if depth < len(queue):
                ordered.append(queue[depth])
                added = True
                if limit is not None and len(ordered) >= limit:
                    break
        if not added:
            break
        depth += 1
    return ordered
