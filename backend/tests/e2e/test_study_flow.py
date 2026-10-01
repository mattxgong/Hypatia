"""E2E study flow (Task 9.10): ingest -> deck -> review -> quiz -> staleness -> backup.

Runs the real app, database, ingestion, and study code with a mock LLM that
answers the ingest, flashcard, quiz, and grading prompts.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.testclient import TestClient

from app.main import app
from app.models.db_models import QuizQuestion
from app.services import wiki_engine
from app.services.prompts.flashcard_prompt import FLASHCARD_SYSTEM_PROMPT
from app.services.prompts.grading_prompt import GRADING_SYSTEM_PROMPT
from app.services.prompts.ingest_prompt import INGEST_SYSTEM_PROMPT
from app.services.prompts.quiz_prompt import QUIZ_SYSTEM_PROMPT
from app.services.study import jobs
from tests.e2e.conftest import MockLLMProvider

pytestmark = pytest.mark.asyncio

VITERBI = "pages/concept/viterbi-algorithm.md"


def _page(slug: str, title: str, body: str) -> str:
    return (
        f'<wiki-page path="pages/concept/{slug}.md">\n---\ntitle: "{title}"\ntype: concept\n'
        f"sources: []\ntags: [sequence-models]\n---\n\n{body}\n</wiki-page>"
    )


_CITE = "[source](hypatia://cite?file=hmm_notes.md&line=3)"
_INGEST_OUTPUT = "\n".join(
    [
        _page(
            "viterbi-algorithm",
            "Viterbi Algorithm",
            "## Definition\n\nThe Viterbi algorithm is a dynamic program that finds the most "
            f"probable state sequence of a Hidden Markov Model.{_CITE}\n\n"
            f"## Complexity\n\nIt runs in \\(O(mk^2)\\) time for \\(k\\) states.{_CITE}",
        ),
        _page(
            "hidden-markov-model",
            "Hidden Markov Model",
            "## Definition\n\nA hidden Markov model is a generative sequence model with hidden "
            f"states that emit observed tokens.{_CITE}",
        ),
        _page(
            "forward-backward-algorithm",
            "Forward-Backward Algorithm",
            "## Definition\n\nThe forward-backward algorithm computes the marginal probability "
            f"of each hidden state given the whole observation sequence.{_CITE}",
        ),
        _page(
            "tokenization",
            "Tokenization",
            "## Definition\n\nTokenization is the process of splitting raw text into tokens "
            f"before a Hidden Markov Model labels them.{_CITE}",
        ),
    ]
)
_CARDS_OUTPUT = (
    f'<card type="basic" page="{VITERBI}"><front>What does Viterbi decoding return?</front>'
    f"<back>The most probable state sequence.{_CITE}</back></card>"
    f'<card type="cloze" page="{VITERBI}"><front>Viterbi runs in {{{{c1::\\(O(mk^2)\\)}}}} '
    "time.</front></card>"
)
_QUIZ_OUTPUT = (
    f'<question type="mcq" page="{VITERBI}"><prompt>What does Viterbi find?</prompt>'
    '<choice correct="true">The most probable state sequence</choice>'
    "<choice>Every state's marginal</choice><choice>The vocabulary</choice>"
    "<choice>The emission matrix</choice></question>"
    f'<question type="short" page="{VITERBI}"><prompt>Why is Viterbi efficient?</prompt>'
    "<answer>It reuses partial results with dynamic programming.</answer>"
    "<rubric>Mentions dynamic programming.</rubric></question>"
)


class StudyMockLLM(MockLLMProvider):
    """Answers the ingest and study prompts with well-formed tagged output."""

    async def complete(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> str:
        responses = {
            INGEST_SYSTEM_PROMPT: _INGEST_OUTPUT,
            FLASHCARD_SYSTEM_PROMPT: _CARDS_OUTPUT,
            QUIZ_SYSTEM_PROMPT: _QUIZ_OUTPUT,
            GRADING_SYSTEM_PROMPT: "<score>0.8</score><feedback>Names the key idea.</feedback>",
        }
        if system_prompt in responses:
            self.call_log.append({"system": system_prompt, "user": user_prompt})
            return responses[system_prompt]
        return await super().complete(system_prompt, user_prompt, max_tokens=max_tokens)


@pytest.fixture
def mock_llm() -> MockLLMProvider:
    return StudyMockLLM()


@pytest.fixture
async def ingested_class(
    e2e_client: AsyncClient,
    e2e_class: dict,
    e2e_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[str]:
    """A class whose uploaded notes went through conversion and LLM ingestion."""
    class_id = e2e_class["id"]
    notes = b"# HMM notes\n\nViterbi decodes the best state path in O(mk^2) time.\n"
    resp = await e2e_client.post(
        f"/api/classes/{class_id}/files",
        files={"files": ("hmm_notes.md", io.BytesIO(notes), "text/markdown")},
    )
    assert resp.status_code == 202
    file_id = uuid.UUID(resp.json()[0]["id"])

    async with e2e_session_factory() as session:
        result = await wiki_engine.ingest_source(session, uuid.UUID(class_id), file_id)
    assert result.success, result.error
    assert len(result.pages_created) == 4
    yield class_id


async def _answers(
    session_factory: async_sessionmaker[AsyncSession], quiz_id: str
) -> dict[str, dict]:
    """Correct responses, read from the stored answer key."""
    async with session_factory() as session:
        questions = await session.scalars(
            select(QuizQuestion).where(QuizQuestion.quiz_id == uuid.UUID(quiz_id))
        )
        answers: dict[str, dict] = {}
        for q in questions:
            key = q.answer_json
            match q.question_type.value:
                case "mcq":
                    answers[str(q.id)] = {"choice": key["choice"]}
                case "tf":
                    answers[str(q.id)] = {"value": key["value"]}
                case "matching":
                    answers[str(q.id)] = {"pairs": key["pairs"]}
                case "fill":
                    answers[str(q.id)] = {"text": key["accepted"][0]}
                case _:
                    answers[str(q.id)] = {"text": "It uses dynamic programming."}
        return answers


class TestOfflineStudyFlow:
    async def test_ingest_to_backup(
        self,
        e2e_client: AsyncClient,
        ingested_class: str,
        e2e_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        base = f"/api/classes/{ingested_class}"

        deck = (await e2e_client.post(f"{base}/decks/generate", json={})).json()
        assert deck["card_count"] >= 4
        assert deck["due_count"] == deck["card_count"]
        deck_url = f"{base}/decks/{deck['id']}"
        cards = (await e2e_client.get(f"{deck_url}/cards")).json()
        assert "What is Viterbi Algorithm?" in {c["front"] for c in cards}
        assert all(c["source_file_ids"] for c in cards)

        [first] = (await e2e_client.get(f"{deck_url}/due", params={"limit": 1})).json()
        resp = await e2e_client.post(
            f"{deck_url}/cards/{first['id']}/review", json={"rating": "good"}
        )
        assert resp.json()["repetitions"] == 1
        assert (await e2e_client.get(deck_url)).json()["due_count"] == deck["card_count"] - 1

        quiz = (
            await e2e_client.post(
                f"{base}/quizzes/generate",
                json={"count": 4, "question_types": ["mcq", "tf", "matching", "fill"], "seed": 1},
            )
        ).json()
        assert quiz["question_count"] >= 3
        attempt = (
            await e2e_client.post(
                f"{base}/quizzes/{quiz['id']}/attempts",
                json={"answers": await _answers(e2e_session_factory, quiz["id"])},
            )
        ).json()
        assert attempt["score"] == attempt["max_score"] == quiz["question_count"]

        page = (await e2e_client.get(f"{base}/wiki/pages/{VITERBI}")).json()
        edited = page["content"] + "\n## Notes\n\nViterbi also works for CRFs.\n"
        assert (
            await e2e_client.put(f"{base}/wiki/pages/{VITERBI}", json={"content": edited})
        ).status_code == 200
        assert (await e2e_client.get(deck_url)).json()["stale_count"] > 0
        assert (await e2e_client.get(f"{base}/quizzes")).json()[0]["stale_count"] > 0
        refreshed = (await e2e_client.post(f"{deck_url}/refresh")).json()
        assert refreshed["remaining_stale"] == 0
        assert (await e2e_client.get(deck_url)).json()["stale_count"] == 0

        export = await e2e_client.get(f"{deck_url}/export", params={"format": "anki"})
        assert export.text.startswith("#separator:tab")

        backup = await e2e_client.post(f"{base}/backup")
        assert backup.status_code == 200
        await e2e_client.put(base, json={"name": "Original copy"})
        imported = await e2e_client.post(
            "/api/classes/import",
            files={"file": ("backup.zip", io.BytesIO(backup.content), "application/zip")},
        )
        assert imported.status_code == 201, imported.text
        new_base = f"/api/classes/{imported.json()['id']}"

        [new_deck] = (await e2e_client.get(f"{new_base}/decks")).json()
        new_cards = (await e2e_client.get(f"{new_base}/decks/{new_deck['id']}/cards")).json()
        assert len(new_cards) == len((await e2e_client.get(f"{deck_url}/cards")).json())
        assert sum(c["repetitions"] for c in new_cards) == 1
        assert new_deck["stale_count"] == 0
        [new_quiz] = (await e2e_client.get(f"{new_base}/quizzes")).json()
        assert new_quiz["attempt_count"] == 1
        assert new_quiz["last_score"] == quiz["question_count"]


class TestAIStudyFlow:
    @pytest.fixture(autouse=True)
    def llm_reachable(self) -> AsyncIterator[None]:
        # The availability probe caches across tests; pin it to "reachable".
        with (
            patch("app.routers.study.check_llm_available", new_callable=AsyncMock),
            patch("app.routers.chat.check_llm_available", new_callable=AsyncMock),
        ):
            yield

    async def test_ai_deck_and_quiz_with_ai_grading(
        self, e2e_client: AsyncClient, ingested_class: str, mock_llm: MockLLMProvider
    ) -> None:
        base = f"/api/classes/{ingested_class}"

        started = await e2e_client.post(
            f"{base}/decks/generate", json={"method": "hybrid", "scope": {"type": "class"}}
        )
        assert started.status_code == 202
        await jobs.wait_for(started.json()["task_id"])
        task = (await e2e_client.get(f"/api/tasks/{started.json()['task_id']}")).json()
        assert task["status"] == "complete", task
        cards = (await e2e_client.get(f"{base}/decks/{task['result']['id']}/cards")).json()
        assert {c["card_type"] for c in cards} == {"basic", "cloze"}
        assert {c["origin"] for c in cards} == {"llm"}
        flashcard_prompt = next(
            c["user"] for c in mock_llm.call_log if c["system"] == FLASHCARD_SYSTEM_PROMPT
        )
        assert "## Draft cards" in flashcard_prompt

        started = await e2e_client.post(
            f"{base}/quizzes/generate",
            json={"method": "llm", "question_types": ["mcq", "short"], "count": 2},
        )
        await jobs.wait_for(started.json()["task_id"])
        task = (await e2e_client.get(f"/api/tasks/{started.json()['task_id']}")).json()
        quiz = (await e2e_client.get(f"{base}/quizzes/{task['result']['id']}")).json()
        short = next(q for q in quiz["questions"] if q["question_type"] == "short")

        attempt = (
            await e2e_client.post(
                f"{base}/quizzes/{quiz['id']}/attempts",
                json={"answers": {short["id"]: {"text": "Dynamic programming."}}},
            )
        ).json()
        result = next(r for r in attempt["results"] if r["question_id"] == short["id"])
        assert (result["grader"], result["score"], result["feedback"]) == (
            "ai",
            0.8,
            "Names the key idea.",
        )

    async def test_flashcards_chat_command(
        self, e2e_client: AsyncClient, ingested_class: str
    ) -> None:
        with (
            TestClient(app) as client,
            client.websocket_connect(f"/api/classes/{ingested_class}/chat") as ws,
        ):
            ws.send_json({"type": "message", "content": "/flashcards viterbi"})
            messages = []
            for _ in range(200):
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

        final = messages[-1]
        assert final["type"] == "complete", messages
        assert final["result"]["command"] == "/flashcards"
        assert final["content"].startswith('Created deck "viterbi flashcards" with 2 cards.')
        decks = (await e2e_client.get(f"/api/classes/{ingested_class}/decks")).json()
        assert [d["generation_method"] for d in decks] == ["llm"]
