"""Study API: decks, review, staleness, export, and quizzes (Task 9.6)."""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import get_session
from app.errors import LLMUnavailableError
from app.main import app
from app.models.db_models import (
    Base,
    Class,
    Deck,
    Flashcard,
    QuizQuestion,
    WikiCategory,
    WikiPage,
)
from app.services.prompts.flashcard_prompt import FLASHCARD_SYSTEM_PROMPT
from app.services.prompts.grading_prompt import GRADING_SYSTEM_PROMPT
from app.services.study import jobs
from app.services.wiki_search import ensure_fts_index, sync_fts_page


def _page(title: str, body: str, tags: str = "[nlp]") -> str:
    return f'---\ntitle: "{title}"\ntype: concept\ntags: {tags}\n---\n\n{body}\n'


PAGES = {
    "pages/concept/viterbi-algorithm.md": (
        "Viterbi Algorithm",
        _page(
            "Viterbi Algorithm",
            "## Definition\n\nThe Viterbi algorithm finds the most probable state sequence "
            "with dynamic programming.[source](hypatia://cite?file=crf.pdf&page=9)\n\n"
            "## Complexity\n\nIt runs in \\(O(mk^2)\\) time for \\(k\\) states.",
        ),
    ),
    "pages/concept/tokenization.md": (
        "Tokenization",
        _page(
            "Tokenization",
            "## Definition\n\nTokenization is the process of segmenting raw text into tokens.",
        ),
    ),
    "pages/concept/sparsity.md": (
        "Sparsity",
        _page(
            "Sparsity",
            "## Definition\n\nSparsity means most linguistic units occur with low frequency.",
        ),
    ),
    "pages/concept/zipf-law.md": (
        "Zipf Law",
        _page(
            "Zipf Law",
            "## Definition\n\nZipf law relates word rank and frequency through a power law, "
            "which is a source of Sparsity in corpora.",
        ),
    ),
    "pages/concept/lemmatization.md": (
        "Lemmatization",
        _page(
            "Lemmatization",
            "## Definition\n\nLemmatization maps inflected words to their dictionary form, "
            "unlike Tokenization which only splits text.",
        ),
    ),
}


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_fts_index(engine)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def class_id(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    class_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(Class(id=class_id, name="NLP"))
        await session.flush()
        for path, (title, content) in PAGES.items():
            page = WikiPage(
                class_id=class_id,
                path=path,
                title=title,
                category=WikiCategory.CONCEPT,
                content=content,
            )
            session.add(page)
            await session.flush()
            await sync_fts_page(session, page.id, class_id, path, title, content)
        await session.commit()
    return class_id


@pytest.fixture
async def client(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _generate_deck(client: AsyncClient, class_id: uuid.UUID, **body: object) -> dict:
    resp = await client.post(f"/api/classes/{class_id}/decks/generate", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestDecks:
    async def test_generate_deck_from_whole_class(
        self, client: AsyncClient, class_id: uuid.UUID
    ) -> None:
        deck = await _generate_deck(client, class_id)
        assert deck["name"] == "All pages flashcards"
        assert deck["generation_method"] == "heuristic"
        assert deck["card_count"] > 0
        assert deck["due_count"] == deck["card_count"]
        assert deck["stale_count"] == 0

        cards = (await client.get(f"/api/classes/{class_id}/decks/{deck['id']}/cards")).json()
        fronts = {c["front"] for c in cards}
        assert "What is Viterbi Algorithm?" in fronts
        assert all(c["origin"] == "heuristic" and c["page_paths"] for c in cards)

        listed = (await client.get(f"/api/classes/{class_id}/decks")).json()
        assert [d["id"] for d in listed] == [deck["id"]]

    async def test_topic_scope_uses_search(self, client: AsyncClient, class_id: uuid.UUID) -> None:
        deck = await _generate_deck(
            client, class_id, scope={"type": "topic", "query": "viterbi"}, card_types=["basic"]
        )
        assert deck["name"] == "viterbi flashcards"
        cards = (await client.get(f"/api/classes/{class_id}/decks/{deck['id']}/cards")).json()
        assert {p for c in cards for p in c["page_paths"]} == {"pages/concept/viterbi-algorithm.md"}

    async def test_pages_scope_and_count_limit(
        self, client: AsyncClient, class_id: uuid.UUID
    ) -> None:
        deck = await _generate_deck(
            client,
            class_id,
            scope={"type": "pages", "paths": ["pages/concept/tokenization.md"]},
            count=1,
            name="Tokens",
        )
        assert deck["name"] == "Tokens"
        assert deck["card_count"] == 1

    async def test_empty_scope_is_a_validation_error(
        self, client: AsyncClient, class_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/api/classes/{class_id}/decks/generate",
            json={"scope": {"type": "topic", "query": "quantum chromodynamics"}},
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "VALIDATION_ERROR"
        assert resp.json()["user_action"]

    async def test_scope_requires_its_fields(
        self, client: AsyncClient, class_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/api/classes/{class_id}/decks/generate", json={"scope": {"type": "topic"}}
        )
        assert resp.status_code == 422

    async def test_unknown_class_and_cross_class_deck(
        self, client: AsyncClient, class_id: uuid.UUID
    ) -> None:
        assert (await client.get(f"/api/classes/{uuid.uuid4()}/decks")).status_code == 404
        deck = await _generate_deck(client, class_id)
        resp = await client.get(f"/api/classes/{uuid.uuid4()}/decks/{deck['id']}")
        assert resp.status_code == 404

    async def test_rename_and_delete(
        self,
        client: AsyncClient,
        class_id: uuid.UUID,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        deck = await _generate_deck(client, class_id)
        url = f"/api/classes/{class_id}/decks/{deck['id']}"
        assert (await client.patch(url, json={"name": "Renamed"})).json()["name"] == "Renamed"
        assert (await client.delete(url)).status_code == 204
        async with session_factory() as session:
            count = await session.scalar(select(func.count()).select_from(Flashcard))
            assert count == 0


class TestReview:
    async def test_review_removes_card_from_due_queue(
        self, client: AsyncClient, class_id: uuid.UUID
    ) -> None:
        deck = await _generate_deck(client, class_id)
        base = f"/api/classes/{class_id}/decks/{deck['id']}"
        due = (await client.get(f"{base}/due", params={"limit": 2})).json()
        assert len(due) == 2

        resp = await client.post(f"{base}/cards/{due[0]['id']}/review", json={"rating": "good"})
        assert resp.status_code == 200
        reviewed = resp.json()
        assert reviewed["repetitions"] == 1
        assert reviewed["interval_days"] == 1
        assert reviewed["last_reviewed_at"] is not None

        remaining = (await client.get(f"{base}/due", params={"limit": 500})).json()
        assert due[0]["id"] not in {c["id"] for c in remaining}
        assert (await client.get(base)).json()["due_count"] == deck["card_count"] - 1

    async def test_invalid_rating(self, client: AsyncClient, class_id: uuid.UUID) -> None:
        deck = await _generate_deck(client, class_id)
        base = f"/api/classes/{class_id}/decks/{deck['id']}"
        card = (await client.get(f"{base}/cards")).json()[0]
        resp = await client.post(f"{base}/cards/{card['id']}/review", json={"rating": "meh"})
        assert resp.status_code == 422


class TestUserCards:
    async def test_create_edit_delete(self, client: AsyncClient, class_id: uuid.UUID) -> None:
        deck = (await client.post(f"/api/classes/{class_id}/decks", json={"name": "Mine"})).json()
        assert deck["card_count"] == 0
        base = f"/api/classes/{class_id}/decks/{deck['id']}/cards"

        resp = await client.post(base, json={"front": "Q?", "back": "A"})
        assert resp.status_code == 201
        card = resp.json()
        assert card["origin"] == "user"
        assert card["stale"] is False

        resp = await client.patch(f"{base}/{card['id']}", json={"back": "Better A"})
        assert resp.json()["back"] == "Better A"
        assert (await client.delete(f"{base}/{card['id']}")).status_code == 204

    async def test_cloze_requires_a_deletion(
        self, client: AsyncClient, class_id: uuid.UUID
    ) -> None:
        deck = (await client.post(f"/api/classes/{class_id}/decks", json={"name": "Mine"})).json()
        base = f"/api/classes/{class_id}/decks/{deck['id']}/cards"
        bad = await client.post(base, json={"card_type": "cloze", "front": "No blank here"})
        assert bad.status_code == 422
        good = await client.post(base, json={"card_type": "cloze", "front": "A {{c1::cat}}."})
        assert good.status_code == 201


class TestStaleness:
    async def _edit_page(
        self, session_factory: async_sessionmaker[AsyncSession], class_id: uuid.UUID, path: str
    ) -> None:
        _, content = PAGES[path]
        async with session_factory() as session:
            await session.execute(
                update(WikiPage)
                .where(WikiPage.class_id == class_id, WikiPage.path == path)
                .values(content=content + "\n## Extra\n\nA new paragraph about the topic here.\n")
            )
            await session.commit()

    async def test_page_edits_mark_cards_stale_and_refresh_fixes_them(
        self,
        client: AsyncClient,
        class_id: uuid.UUID,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        deck = await _generate_deck(client, class_id)
        base = f"/api/classes/{class_id}/decks/{deck['id']}"
        path = "pages/concept/viterbi-algorithm.md"
        await self._edit_page(session_factory, class_id, path)

        cards = (await client.get(f"{base}/cards")).json()
        stale = [c for c in cards if c["stale"]]
        assert stale and all(path in c["page_paths"] for c in stale)
        assert (await client.get(base)).json()["stale_count"] == len(stale)

        refreshed = (await client.post(f"{base}/refresh")).json()
        assert refreshed["updated"] + refreshed["removed"] == len(stale)
        assert refreshed["remaining_stale"] == 0
        assert (await client.get(base)).json()["stale_count"] == 0

    async def test_frontmatter_only_changes_are_not_stale(
        self,
        client: AsyncClient,
        class_id: uuid.UUID,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        deck = await _generate_deck(client, class_id)
        async with session_factory() as session:
            page = await session.scalar(
                select(WikiPage).where(WikiPage.path == "pages/concept/sparsity.md")
            )
            assert page is not None
            page.content = page.content.replace("tags: [nlp]", "tags: [nlp, corpora]")
            await session.commit()
        assert (await client.get(f"/api/classes/{class_id}/decks/{deck['id']}")).json()[
            "stale_count"
        ] == 0

    async def test_acknowledging_changes_clears_stale(
        self,
        client: AsyncClient,
        class_id: uuid.UUID,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        deck = await _generate_deck(client, class_id)
        base = f"/api/classes/{class_id}/decks/{deck['id']}"
        path = "pages/concept/tokenization.md"
        await self._edit_page(session_factory, class_id, path)
        card = next(c for c in (await client.get(f"{base}/cards")).json() if c["stale"])

        resp = await client.patch(f"{base}/cards/{card['id']}", json={"acknowledge_changes": True})
        assert resp.json()["stale"] is False
        assert resp.json()["page_paths"] == card["page_paths"]


class TestExport:
    async def test_csv_and_anki(self, client: AsyncClient, class_id: uuid.UUID) -> None:
        deck = await _generate_deck(client, class_id)
        base = f"/api/classes/{class_id}/decks/{deck['id']}/export"

        resp = await client.get(base, params={"format": "csv"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert 'filename="All-pages-flashcards.csv"' in resp.headers["content-disposition"]
        rows = list(csv.reader(io.StringIO(resp.text)))
        assert rows[0] == ["front", "back"]
        assert len(rows) == deck["card_count"] + 1
        assert not any("hypatia://" in cell for row in rows for cell in row)
        assert not any("{{c1::" in row[0] for row in rows)

        resp = await client.get(base, params={"format": "anki"})
        lines = resp.text.splitlines()
        assert lines[:5] == [
            "#separator:tab",
            "#html:false",
            "#notetype column:1",
            "#tags column:4",
            "#deck:All pages flashcards",
        ]
        kinds = {line.split("\t")[0] for line in lines[5:]}
        assert kinds <= {"Basic", "Cloze"}
        assert (await client.get(base, params={"format": "pdf"})).status_code == 422


class TestQuizzes:
    async def test_generate_take_and_score(
        self,
        client: AsyncClient,
        class_id: uuid.UUID,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        resp = await client.post(
            f"/api/classes/{class_id}/quizzes/generate",
            json={"count": 6, "question_types": ["mcq", "tf", "fill"], "seed": 4},
        )
        assert resp.status_code == 201, resp.text
        quiz = resp.json()
        assert quiz["question_count"] == len(quiz["questions"]) > 0
        assert quiz["settings_json"]["ai_grading"] is True
        assert quiz["settings_json"]["seed"] == 4
        assert all("answer_json" not in q and "answer" not in q for q in quiz["questions"])

        async with session_factory() as session:
            rows = await session.scalars(
                select(QuizQuestion).where(QuizQuestion.quiz_id == uuid.UUID(quiz["id"]))
            )
            answers = {}
            for q in rows:
                if q.question_type.value == "mcq":
                    answers[str(q.id)] = {"choice": q.answer_json["choice"]}
                elif q.question_type.value == "tf":
                    answers[str(q.id)] = {"value": q.answer_json["value"]}
                else:
                    answers[str(q.id)] = {"text": q.answer_json["accepted"][0].upper()}

        base = f"/api/classes/{class_id}/quizzes/{quiz['id']}"
        resp = await client.post(f"{base}/attempts", json={"answers": answers})
        assert resp.status_code == 201
        attempt = resp.json()
        assert attempt["score"] == attempt["max_score"] == quiz["question_count"]
        assert all(r["correct"] and r["expected"] for r in attempt["results"])

        empty = (await client.post(f"{base}/attempts", json={"answers": {}})).json()
        assert empty["score"] == 0
        assert {r["status"] for r in empty["results"]} == {"unanswered"}

        summary = (await client.get(f"/api/classes/{class_id}/quizzes")).json()[0]
        assert summary["attempt_count"] == 2
        assert summary["last_score"] == 0
        assert len((await client.get(f"{base}/attempts")).json()) == 2

        assert (await client.delete(base)).status_code == 204
        assert (await client.get(base)).status_code == 404

    async def test_short_answer_needs_ai(self, client: AsyncClient, class_id: uuid.UUID) -> None:
        resp = await client.post(
            f"/api/classes/{class_id}/quizzes/generate", json={"question_types": ["short"]}
        )
        assert resp.status_code == 422


VITERBI_PATH = "pages/concept/viterbi-algorithm.md"


def _ai_output(system: str, _: str) -> str:
    if system == GRADING_SYSTEM_PROMPT:
        return "<score>0.9</score><feedback>Covers the key point.</feedback>"
    if system == FLASHCARD_SYSTEM_PROMPT:
        return (
            f'<card type="basic" page="{VITERBI_PATH}"><front>Why use Viterbi?</front>'
            "<back>It finds the most probable state sequence.</back></card>"
            '<card type="basic" page="pages/concept/missing.md"><front>Uncited?</front>'
            "<back>x</back></card>"
        )
    return (
        f'<question type="short" page="{VITERBI_PATH}"><prompt>What does Viterbi find?</prompt>'
        "<answer>The most probable state sequence.</answer></question>"
        f'<question type="tf" page="{VITERBI_PATH}"><prompt>Viterbi uses dynamic programming.'
        "</prompt><answer>true</answer></question>"
    )


@pytest.fixture
def ai(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> AsyncMock:
    """Reachable fake LLM; background jobs use the test database. Returns the LLM check."""
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=lambda system, user, **_: _ai_output(system, user))
    provider.close = AsyncMock()
    monkeypatch.setattr("app.database.async_session_factory", session_factory)
    monkeypatch.setattr("app.services.study.llm_generator.get_llm_provider", lambda: provider)
    check = AsyncMock()
    monkeypatch.setattr("app.routers.study.check_llm_available", check)
    return check


async def _start_ai_job(client: AsyncClient, url: str, body: dict) -> dict:
    resp = await client.post(url, json=body)
    assert resp.status_code == 202, resp.text
    started = resp.json()
    await jobs.wait_for(started["task_id"])
    task = (await client.get(f"/api/tasks/{started['task_id']}")).json()
    assert task["status"] == "complete", task
    return task


class TestAIGeneration:
    async def test_llm_deck_runs_as_a_task(
        self, client: AsyncClient, class_id: uuid.UUID, ai: AsyncMock
    ) -> None:
        task = await _start_ai_job(
            client,
            f"/api/classes/{class_id}/decks/generate",
            {"method": "llm", "scope": {"type": "topic", "query": "viterbi"}},
        )
        assert task["operation"] == "Generate flashcards"
        assert task["result"]["kind"] == "deck"
        assert task["result"]["count"] == "1"

        base = f"/api/classes/{class_id}/decks/{task['result']['id']}"
        deck = (await client.get(base)).json()
        assert deck["generation_method"] == "llm"
        [card] = (await client.get(f"{base}/cards")).json()
        assert card["origin"] == "llm"
        assert card["page_paths"] == [VITERBI_PATH]

    async def test_unreachable_llm_is_rejected_up_front(
        self, client: AsyncClient, class_id: uuid.UUID, ai: AsyncMock
    ) -> None:
        ai.side_effect = LLMUnavailableError()
        resp = await client.post(
            f"/api/classes/{class_id}/decks/generate", json={"method": "hybrid"}
        )
        assert resp.status_code == 503
        assert resp.json()["code"] == "LLM_UNAVAILABLE"

    async def test_empty_scope_fails_before_starting(
        self, client: AsyncClient, class_id: uuid.UUID, ai: AsyncMock
    ) -> None:
        resp = await client.post(
            f"/api/classes/{class_id}/quizzes/generate",
            json={"method": "llm", "scope": {"type": "topic", "query": "quantum"}},
        )
        assert resp.status_code == 422
        ai.assert_not_awaited()

    async def test_short_answers_are_ai_graded(
        self, client: AsyncClient, class_id: uuid.UUID, ai: AsyncMock
    ) -> None:
        task = await _start_ai_job(
            client,
            f"/api/classes/{class_id}/quizzes/generate",
            {"method": "hybrid", "question_types": ["short", "tf"], "count": 2},
        )
        base = f"/api/classes/{class_id}/quizzes/{task['result']['id']}"
        quiz = (await client.get(base)).json()
        assert quiz["generation_method"] == "hybrid"
        short = next(q for q in quiz["questions"] if q["question_type"] == "short")
        tf = next(q for q in quiz["questions"] if q["question_type"] == "tf")
        answers = {short["id"]: {"text": "the best path"}, tf["id"]: {"value": True}}

        attempt = (await client.post(f"{base}/attempts", json={"answers": answers})).json()
        result = next(r for r in attempt["results"] if r["question_id"] == short["id"])
        assert result["grader"] == "ai"
        assert result["score"] == 0.9
        assert result["correct"] is True
        assert result["feedback"] == "Covers the key point."
        assert attempt["score"] == pytest.approx(1.9)

    async def test_self_review_when_ai_grading_is_off(
        self, client: AsyncClient, class_id: uuid.UUID, ai: AsyncMock
    ) -> None:
        task = await _start_ai_job(
            client,
            f"/api/classes/{class_id}/quizzes/generate",
            {"method": "llm", "question_types": ["short"], "count": 1, "ai_grading": False},
        )
        base = f"/api/classes/{class_id}/quizzes/{task['result']['id']}"
        [short] = (await client.get(base)).json()["questions"]

        attempt = (
            await client.post(
                f"{base}/attempts", json={"answers": {short["id"]: {"text": "a path"}}}
            )
        ).json()
        [result] = attempt["results"]
        assert result["status"] == "needs_self_review"
        assert result["expected"]["reference"] == "The most probable state sequence."

        resp = await client.patch(
            f"{base}/attempts/{attempt['id']}", json={"grades": {short["id"]: True}}
        )
        [graded] = resp.json()["results"]
        assert (graded["status"], graded["grader"], graded["score"]) == ("graded", "self", 1.0)
        assert resp.json()["score"] == 1.0

    async def test_heuristic_refresh_leaves_ai_cards_alone(
        self,
        client: AsyncClient,
        class_id: uuid.UUID,
        ai: AsyncMock,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        task = await _start_ai_job(
            client, f"/api/classes/{class_id}/decks/generate", {"method": "llm"}
        )
        async with session_factory() as session:
            await session.execute(
                update(WikiPage)
                .where(WikiPage.path == VITERBI_PATH)
                .values(content=PAGES[VITERBI_PATH][1] + "\nMore text here.\n")
            )
            await session.commit()
        base = f"/api/classes/{class_id}/decks/{task['result']['id']}"
        refreshed = (await client.post(f"{base}/refresh")).json()
        assert refreshed == {"updated": 0, "removed": 0, "remaining_stale": 1}


async def test_deleting_a_class_removes_study_data(
    client: AsyncClient,
    class_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _generate_deck(client, class_id)
    async with session_factory() as session:
        class_ = await session.get(Class, class_id)
        assert class_ is not None
        await session.delete(class_)
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(Deck)) == 0
        assert await session.scalar(select(func.count()).select_from(Flashcard)) == 0
