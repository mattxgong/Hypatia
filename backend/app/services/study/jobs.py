"""Background jobs for AI study generation (Task 9.5).

Generation runs outside the request so the UI and chat stay responsive; the
task registry reports progress and, on success, which deck or quiz was made.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Literal

from app import database
from app.errors import HypatiaError
from app.models.schemas import DeckGenerateRequest, QuizGenerateRequest
from app.services.study import service
from app.services.study.llm_generator import GenerationCancelled
from app.services.task_manager import task_manager
from app.utils.logging import get_logger

logger = get_logger()

StudyKind = Literal["deck", "quiz"]

_OPERATIONS: dict[StudyKind, str] = {"deck": "Generate flashcards", "quiz": "Generate quiz"}
_running: dict[str, asyncio.Task[None]] = {}


def start_generation(
    kind: StudyKind, class_id: uuid.UUID, request: DeckGenerateRequest | QuizGenerateRequest
) -> str:
    task_id = task_manager.start_task(_OPERATIONS[kind], str(class_id))
    job = asyncio.create_task(_run(kind, class_id, request, task_id))
    _running[task_id] = job
    job.add_done_callback(lambda _: _running.pop(task_id, None))
    return task_id


async def wait_for(task_id: str) -> None:
    job = _running.get(task_id)
    if job is not None:
        await job


async def _run(
    kind: StudyKind,
    class_id: uuid.UUID,
    request: DeckGenerateRequest | QuizGenerateRequest,
    task_id: str,
) -> None:
    async with database.async_session_factory() as session:
        try:
            if isinstance(request, DeckGenerateRequest):
                deck = await service.generate_deck_with_llm(session, class_id, request, task_id)
                count = len(await service.deck_cards(session, deck.id))
                result = {"kind": kind, "id": str(deck.id), "name": deck.name, "count": str(count)}
            else:
                quiz = await service.generate_quiz_with_llm(session, class_id, request, task_id)
                count = len(await service.quiz_questions(session, quiz.id))
                result = {"kind": kind, "id": str(quiz.id), "name": quiz.name, "count": str(count)}
        except GenerationCancelled:
            logger.info("study_generation_cancelled", task_id=task_id)
            return
        except HypatiaError as e:
            logger.warning("study_generation_failed", task_id=task_id, error=e.detail)
            task_manager.fail_task(task_id, e.detail)
            return
        except Exception as e:
            logger.exception("study_generation_error", task_id=task_id)
            task_manager.fail_task(task_id, str(e))
            return
    task_manager.complete_task(task_id, result)
