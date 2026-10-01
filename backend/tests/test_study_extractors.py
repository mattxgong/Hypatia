"""Heuristic flashcard extraction (Task 9.2)."""

from __future__ import annotations

from app.models.db_models import CardType
from app.services.study.extractors import (
    body_hash,
    cards_from_definitions,
    cards_from_page_lead,
    cards_from_sections,
    cards_from_tables,
    cloze_from_key_terms,
    generate_cards,
    parse_page,
    resolve_wiki_links,
)

CRF_PAGE = """---
title: "Conditional Random Fields"
type: concept
sources: [file-1]
tags: [crf, sequence-labeling]
---

## Definition

A conditional random field (CRF) is a globally normalized [[log-linear-models|log-linear model]] over state sequences.[source](hypatia://cite?file=crf.pdf&page=7) It conditions on the input \\(x\\).[source](hypatia://cite?file=crf.pdf&page=7)

## Decoding

Decoding uses a [[viterbi-algorithm]]-style dynamic program in \\(O(mk^2)\\) time.[source](hypatia://cite?file=crf.pdf&page=9)

The conditional probability is

\\[
p(s \\mid x; w) = \\frac{\\exp(w \\cdot \\Phi(x,s))}{Z}
\\]

which normalizes globally.

## Related Pages

See [[viterbi-algorithm]] and [[log-linear-models]] for the Viterbi Algorithm details.
"""

SLUG_TITLES = {
    "conditional-random-fields": "Conditional Random Fields",
    "viterbi-algorithm": "Viterbi Algorithm",
    "log-linear-models": "Log-Linear Models",
}


def _crf():
    return parse_page(
        "pages/concept/conditional-random-fields.md",
        "Conditional Random Fields",
        "concept",
        CRF_PAGE,
        ["file-1"],
    )


def _page(body: str, *, title: str = "Entropy", category: str = "concept", path: str = ""):
    return parse_page(path or f"pages/{category}/{title.lower()}.md", title, category, body)


class TestParsing:
    def test_frontmatter_tags_and_sources(self) -> None:
        doc = _crf()
        assert doc.tags == ["crf", "sequence-labeling"]
        assert doc.source_file_ids == ["file-1"]
        assert not doc.body.startswith("---")

    def test_body_hash_ignores_frontmatter(self) -> None:
        bumped = CRF_PAGE.replace("sources: [file-1]", "sources: [file-1, file-2]")
        assert body_hash(bumped) == body_hash(CRF_PAGE)
        assert body_hash(CRF_PAGE.replace("O(mk^2)", "O(mk^3)")) != body_hash(CRF_PAGE)

    def test_resolve_wiki_links(self) -> None:
        text = "Uses [[viterbi-algorithm]] and [[log-linear-models|a log-linear model]]."
        assert resolve_wiki_links(text, SLUG_TITLES) == (
            "Uses Viterbi Algorithm and a log-linear model."
        )


class TestPageLead:
    def test_uses_definition_section_and_keeps_math_and_citations(self) -> None:
        [card] = cards_from_page_lead(_crf())
        assert card.front == "What are Conditional Random Fields?"
        assert card.back.startswith("A conditional random field (CRF) is")
        assert "\\(x\\)" in card.back
        assert card.back.count("hypatia://cite") == 2
        assert card.subject == "Conditional Random Fields"
        assert card.card_type == CardType.BASIC

    def test_entity_phrasing(self) -> None:
        doc = _page(
            "## Overview\n\nMichael Collins wrote the note on sequence models.",
            title="Michael Collins",
            category="entity",
        )
        [card] = cards_from_page_lead(doc)
        assert card.front == "Who or what is Michael Collins?"

    def test_falls_back_to_first_paragraph(self) -> None:
        doc = _page("Entropy measures the uncertainty of a random variable.")
        [card] = cards_from_page_lead(doc)
        assert card.front == "What is Entropy?"

    def test_source_summaries_and_bare_pages_yield_nothing(self) -> None:
        summary = _page("Summary text that is long enough to be a card.", category="source-summary")
        assert cards_from_page_lead(summary) == []
        assert cards_from_page_lead(_page("## Notes\n\n- a\n- b")) == []


class TestSections:
    def test_skips_lead_and_related_sections_and_fragments(self) -> None:
        cards = cards_from_sections(_crf())
        assert [c.front for c in cards] == ["Conditional Random Fields: Decoding"]
        assert "O(mk^2)" in cards[0].back
        assert "which normalizes" not in cards[0].back


class TestDefinitions:
    def test_bold_definition_lines(self) -> None:
        doc = _page(
            "- **Entropy**: the expected information content of a variable.\n"
            "- **Perplexity** is the exponentiated cross-entropy of a model.",
            title="Information Theory",
        )
        cards = cards_from_definitions(doc, {}, {})
        fronts = {c.front: c.back for c in cards}
        assert fronts["What is Entropy?"] == "the expected information content of a variable."
        assert fronts["What is Perplexity?"].startswith("Perplexity is the exponentiated")

    def test_sentence_definition_of_known_term_on_another_page(self) -> None:
        doc = _page(
            "The Viterbi algorithm is a dynamic program that finds the best state sequence.",
            title="Decoding",
        )
        known = {"viterbi algorithm": "Viterbi Algorithm"}
        [card] = cards_from_definitions(doc, known, SLUG_TITLES)
        assert card.front == "What is Viterbi Algorithm?"

    def test_ignores_definitions_of_the_page_itself(self) -> None:
        doc = _page("Entropy is a measure of uncertainty in a distribution.")
        assert cards_from_definitions(doc, {"entropy": "Entropy"}, {}) == []


class TestTables:
    def test_two_column_table_rows(self) -> None:
        doc = _page(
            "| Model | Normalization |\n|---|---|\n| MEMM | local |\n| CRF | global |",
            title="Comparison",
        )
        cards = cards_from_tables(doc)
        assert [(c.front, c.back) for c in cards] == [
            ("MEMM \u2014 Normalization", "local"),
            ("CRF \u2014 Normalization", "global"),
        ]

    def test_wider_tables_are_ignored(self) -> None:
        doc = _page("| a | b | c |\n|---|---|---|\n| 1 | 2 | 3 |")
        assert cards_from_tables(doc) == []


class TestCloze:
    def test_clozes_one_known_term_outside_math_and_related_sections(self) -> None:
        doc = _crf()
        cards = cloze_from_key_terms(
            doc, ["Viterbi Algorithm", "Conditional Random Fields"], {}, SLUG_TITLES
        )
        fronts = [c.front for c in cards]
        assert any("{{c1::Viterbi Algorithm}}" in f for f in fronts)
        assert all("Related" not in f and not f.startswith("See") for f in fronts)
        viterbi = next(c for c in cards if c.back == "Viterbi Algorithm")
        assert "\\(O(mk^2)\\)" in viterbi.front
        assert viterbi.card_type == CardType.CLOZE

    def test_skips_sentences_where_the_term_repeats(self) -> None:
        doc = _page("Entropy is high when entropy of each outcome is equal across outcomes.")
        assert cloze_from_key_terms(doc, ["Entropy"], {}, {}) == []


class TestGenerateCards:
    def test_dedupes_and_interleaves_pages(self) -> None:
        other = _page(
            "## Definition\n\nThe Viterbi algorithm finds the most probable state sequence.",
            title="Viterbi Algorithm",
            path="pages/concept/viterbi-algorithm.md",
        )
        cards = generate_cards([_crf(), other], slug_titles=SLUG_TITLES, limit=3)
        assert len(cards) == 3
        assert cards[0].page_path.endswith("conditional-random-fields.md")
        assert cards[1].page_path.endswith("viterbi-algorithm.md")
        fronts = [c.front for c in generate_cards([_crf(), other], slug_titles=SLUG_TITLES)]
        assert len(fronts) == len(set(fronts))

    def test_card_type_filter(self) -> None:
        cards = generate_cards([_crf()], slug_titles=SLUG_TITLES, card_types=[CardType.CLOZE])
        assert cards and all(c.card_type == CardType.CLOZE for c in cards)

    def test_index_and_log_pages_are_skipped(self) -> None:
        index = _page("Entropy is listed here as a concept page.", title="Index", category="index")
        assert generate_cards([index], slug_titles={}) == []
