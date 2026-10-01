"""Heuristic quiz assembly and grading (Task 9.3)."""

from __future__ import annotations

from app.models.db_models import CardType, QuestionType
from app.services.study.extractors import CardCandidate
from app.services.study.grading import grade, normalize_answer
from app.services.study.quiz_builder import BLANK, build_quiz, cloze_prompt, redact

ALL_TYPES = [QuestionType.MCQ, QuestionType.TRUE_FALSE, QuestionType.MATCHING, QuestionType.FILL]


def _basic(term: str, back: str, *, tags: list[str] | None = None) -> CardCandidate:
    return CardCandidate(
        front=f"What is {term}?",
        back=back,
        card_type=CardType.BASIC,
        page_path=f"pages/concept/{term.lower().replace(' ', '-')}.md",
        source_file_ids=["file-1"],
        tags=tags or [],
        label=term,
        subject=term,
    )


def _cloze(term: str, sentence: str) -> CardCandidate:
    return CardCandidate(
        front=sentence.replace(term, f"{{{{c1::{term}}}}}"),
        back=term,
        card_type=CardType.CLOZE,
        page_path=f"pages/concept/{term.lower()}.md",
        label=term,
    )


def _pool() -> list[CardCandidate]:
    return [
        _basic("Entropy", "Entropy measures uncertainty in a distribution.", tags=["info"]),
        _basic("Perplexity", "Perplexity is exponentiated cross-entropy.", tags=["info"]),
        _basic("Tokenization", "Tokenization splits raw text into tokens."),
        _basic("Sparsity", "Sparsity means most units are rare in a corpus."),
        _basic("Zipf Law", "Zipf law relates word rank to frequency by a power law."),
        _basic("Lemma", "A lemma is the dictionary form of a word."),
        _basic("Corpus", "A corpus is a large structured collection of texts."),
        _basic("Stemming", "Stemming strips affixes to reduce words to a crude root."),
        _basic("Bigram", "A bigram is a sequence of two adjacent tokens."),
        _cloze("Viterbi", "The Viterbi algorithm decodes the best state sequence."),
        _cloze("Softmax", "The Softmax function turns scores into probabilities."),
    ]


class TestRedact:
    def test_hides_subject_but_not_math_or_citations(self) -> None:
        text = "Entropy \\(H(X)\\) of entropy sources.[Entropy](hypatia://cite?file=a.pdf)"
        assert redact(text, "Entropy") == (
            f"{BLANK} \\(H(X)\\) of {BLANK} sources.[Entropy](hypatia://cite?file=a.pdf)"
        )

    def test_hides_wiki_links_and_abbreviations_for_subject(self) -> None:
        text = "A conditional random field (CRF) extends [[conditional-random-fields]] ideas."
        assert redact(text, "Conditional Random Fields") == f"A {BLANK} extends {BLANK} ideas."

    def test_cloze_prompt(self) -> None:
        assert cloze_prompt("The {{c1::Viterbi}} algorithm.") == f"The {BLANK} algorithm."


class TestBuildQuiz:
    def test_cycles_types_and_is_deterministic(self) -> None:
        first = build_quiz(_pool(), question_types=ALL_TYPES, count=5, seed=7)
        second = build_quiz(_pool(), question_types=ALL_TYPES, count=5, seed=7)
        assert [q.question_type for q in first] == [q.question_type for q in second]
        assert [q.answer for q in first] == [q.answer for q in second]
        assert {q.question_type for q in first} == set(ALL_TYPES)

    def test_mcq_has_unique_options_and_one_correct_answer(self) -> None:
        pool = _pool()
        [mcq] = build_quiz(pool, question_types=[QuestionType.MCQ], count=1, seed=3)
        options = mcq.choices["options"] if mcq.choices else []
        assert len(options) == len(set(options)) == 4
        correct = options[mcq.answer["choice"]]
        source = next(c for c in pool if c.front == mcq.prompt)
        assert correct == redact(source.back, source.subject)
        assert BLANK in correct
        assert mcq.page_paths == [source.page_path]

    def test_matching_answer_maps_left_to_right(self) -> None:
        [matching] = build_quiz(_pool(), question_types=[QuestionType.MATCHING], count=1, seed=1)
        assert matching.choices is not None
        left, right = matching.choices["left"], matching.choices["right"]
        assert len(left) == 4
        for i, target in enumerate(matching.answer["pairs"]):
            assert right[target].endswith(next(c.back for c in _pool() if c.label == left[i])[-10:])

    def test_unavailable_types_drop_out(self) -> None:
        only_basic = [c for c in _pool() if c.card_type == CardType.BASIC]
        questions = build_quiz(only_basic, question_types=[QuestionType.FILL], count=3, seed=1)
        assert questions == []
        fill = build_quiz(_pool(), question_types=[QuestionType.FILL], count=5, seed=1)
        assert len(fill) == 2
        assert fill[0].answer["accepted"][0] in {"Viterbi", "Softmax"}

    def test_mcq_needs_enough_distractors(self) -> None:
        pool = _pool()[:3]
        assert build_quiz(pool, question_types=[QuestionType.MCQ], count=1, seed=1) == []


class TestGrading:
    def test_normalize_answer(self) -> None:
        assert normalize_answer("  The Viterbi Algorithms! ") == "viterbi algorithm"
        assert normalize_answer("Café") == "cafe"

    def test_mcq_and_true_false(self) -> None:
        assert grade(QuestionType.MCQ, {"choice": 2}, {"choice": 2}).correct is True
        assert grade(QuestionType.MCQ, {"choice": 2}, {"choice": 1}).score == 0.0
        assert grade(QuestionType.TRUE_FALSE, {"value": False}, {"value": False}).correct is True
        assert grade(QuestionType.TRUE_FALSE, {"value": False}, {"value": 0}).correct is False

    def test_fill_is_lenient_about_case_articles_and_plurals(self) -> None:
        answer = {"accepted": ["Viterbi algorithm"]}
        assert grade(QuestionType.FILL, answer, {"text": "the viterbi algorithms"}).correct
        assert not grade(QuestionType.FILL, answer, {"text": "forward algorithm"}).correct

    def test_matching_gives_partial_credit(self) -> None:
        result = grade(QuestionType.MATCHING, {"pairs": [0, 1, 2, 3]}, {"pairs": [0, 1, 3, 2]})
        assert result.score == 0.5
        assert result.correct is False

    def test_unanswered_and_malformed(self) -> None:
        assert grade(QuestionType.MCQ, {"choice": 0}, None).status == "unanswered"
        assert grade(QuestionType.FILL, {"accepted": ["x"]}, {"text": 5}).status == "unanswered"
        assert grade(QuestionType.SHORT, {"reference": "x"}, None).status == "unanswered"
        assert grade(QuestionType.SHORT, {}, {"text": "  "}).status == "unanswered"
        short = grade(QuestionType.SHORT, {"reference": "x"}, {"text": "an answer"})
        assert (short.status, short.correct) == ("needs_self_review", None)
        assert grade(QuestionType.SHORT, {}, {"self_grade": True}).correct is True
