"""Chat WebSocket + history endpoints (Task 4.6).

Implements the ChatWs* protocol from docs/api-contract.yaml:
- Client sends ChatWsMessage → parsed into command → routed to handler
- Server streams ChatWsChunk → ChatWsComplete for /ask
- Server sends ChatWsProgress for long-running ops, supports ChatWsCancel
- Server sends ChatWsError on failures
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory, get_session
from app.errors import ErrorCode, HypatiaError
from app.models.db_models import ChatMessage, ChatRole
from app.models.schemas import ChatMessageRead
from app.services import wiki_engine
from app.services.task_manager import task_manager
from app.utils.command_parser import parse_command
from app.utils.logging import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/classes/{class_id}/chat", tags=["chat"])


@router.websocket("")
async def chat_websocket(websocket: WebSocket, class_id: uuid.UUID) -> None:
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "cancel":
                op_id = data.get("operation_id")
                if op_id:
                    task_manager.cancel_task(op_id)
                continue

            content = data.get("content", "")
            try:
                parsed = parse_command(content)
            except ValueError as e:
                await websocket.send_json(
                    {"type": "error", "message": str(e), "code": "INVALID_COMMAND"}
                )
                continue

            await _handle_command(websocket, class_id, parsed.command, parsed.args)

    except WebSocketDisconnect:
        logger.debug("chat_ws_disconnected", class_id=str(class_id))


async def _handle_command(
    websocket: WebSocket, class_id: uuid.UUID, command: str, args: str
) -> None:
    if command == "help":
        await _handle_help(websocket)
    elif command == "ask":
        await _handle_ask_stream(websocket, class_id, args)
    elif command == "summarize":
        await _handle_summarize(websocket, class_id, args)
    elif command == "remove":
        await _handle_remove(websocket, class_id, args)
    elif command == "lint":
        await _handle_lint(websocket, class_id)
    elif command == "export":
        await _handle_export(websocket, class_id)
    elif command == "rebuild":
        await _handle_rebuild(websocket, class_id)


_HELP_TEXT = """\
**Available Commands**

| Command | Description |
|---------|-------------|
| `/ask <query>` | Ask a question — answers from the wiki with citations |
| `/summarize <topic>` | Generate a new wiki summary page on a topic |
| `/remove <filename>` | Remove a source file and clean up its wiki pages |
| `/lint` | Check the wiki for contradictions and structural issues |
| `/rebuild` | Regenerate the entire wiki from all sources |
| `/export` | Export the wiki as markdown files |
| `/help` | Show this command reference |

Type a message without a `/` prefix to default to `/ask`."""


async def _handle_help(websocket: WebSocket) -> None:
    await websocket.send_json(
        {
            "type": "complete",
            "message_id": str(uuid.uuid4()),
            "content": _HELP_TEXT,
        }
    )


async def _handle_ask_stream(websocket: WebSocket, class_id: uuid.UUID, query: str) -> None:
    async with async_session_factory() as session:
        try:
            session.add(ChatMessage(class_id=class_id, role=ChatRole.USER, content=query))
            await session.commit()

            chunks: list[str] = []
            async for chunk in wiki_engine.handle_ask_stream(session, class_id, query):
                chunks.append(chunk)
                await websocket.send_json({"type": "chunk", "content": chunk})

            msg_id = str(uuid.uuid4())
            session.add(
                ChatMessage(
                    class_id=class_id,
                    role=ChatRole.ASSISTANT,
                    content="".join(chunks),
                    command="ask",
                )
            )
            await session.commit()

            await websocket.send_json(
                {
                    "type": "complete",
                    "message_id": msg_id,
                    "citations": [],
                }
            )
        except HypatiaError as e:
            logger.error("chat_ask_error", class_id=str(class_id), code=e.code.value)
            await websocket.send_json(
                {
                    "type": "error",
                    "message": e.detail,
                    "code": e.code.value,
                    "user_action": e.user_action,
                }
            )
        except Exception as e:  # noqa: BLE001
            logger.error("chat_ask_error", class_id=str(class_id), error=str(e))
            await websocket.send_json(
                {
                    "type": "error",
                    "message": str(e),
                    "code": ErrorCode.ASK_ERROR,
                }
            )


async def _handle_summarize(websocket: WebSocket, class_id: uuid.UUID, topic: str) -> None:
    async with async_session_factory() as session:
        try:
            session.add(
                ChatMessage(class_id=class_id, role=ChatRole.USER, content=f"/summarize {topic}")
            )
            await session.commit()

            result = await wiki_engine.handle_summarize(session, class_id, topic)
            if result.success:
                session.add(
                    ChatMessage(
                        class_id=class_id,
                        role=ChatRole.ASSISTANT,
                        content=f"Created summary page: {result.page_path}",
                        command="summarize",
                    )
                )
                await session.commit()
                await websocket.send_json(
                    {
                        "type": "complete",
                        "message_id": str(uuid.uuid4()),
                        "result": {"page_path": result.page_path},
                    }
                )
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": result.error or "Summarize failed",
                        "code": "SUMMARIZE_ERROR",
                    }
                )
        except HypatiaError as e:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": e.detail,
                    "code": e.code.value,
                    "user_action": e.user_action,
                }
            )
        except Exception as e:  # noqa: BLE001
            await websocket.send_json(
                {"type": "error", "message": str(e), "code": ErrorCode.SUMMARIZE_ERROR}
            )


async def _handle_remove(websocket: WebSocket, class_id: uuid.UUID, filename: str) -> None:
    async with async_session_factory() as session:
        try:
            session.add(
                ChatMessage(class_id=class_id, role=ChatRole.USER, content=f"/remove {filename}")
            )
            await session.commit()

            result = await wiki_engine.handle_remove(session, class_id, filename)
            if result.success:
                session.add(
                    ChatMessage(
                        class_id=class_id,
                        role=ChatRole.ASSISTANT,
                        content=f"Removed {filename}: {result.pages_deleted} pages deleted, {result.pages_updated} pages updated",
                        command="remove",
                    )
                )
                await session.commit()
                await websocket.send_json(
                    {
                        "type": "complete",
                        "message_id": str(uuid.uuid4()),
                        "result": {
                            "pages_deleted": result.pages_deleted,
                            "pages_updated": result.pages_updated,
                        },
                    }
                )
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": result.error or "Remove failed",
                        "code": "REMOVE_ERROR",
                    }
                )
        except HypatiaError as e:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": e.detail,
                    "code": e.code.value,
                    "user_action": e.user_action,
                }
            )
        except Exception as e:  # noqa: BLE001
            await websocket.send_json(
                {"type": "error", "message": str(e), "code": ErrorCode.REMOVE_ERROR}
            )


async def _handle_lint(websocket: WebSocket, class_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        try:
            session.add(ChatMessage(class_id=class_id, role=ChatRole.USER, content="/lint"))
            await session.commit()

            result = await wiki_engine.handle_lint(session, class_id)

            session.add(
                ChatMessage(
                    class_id=class_id,
                    role=ChatRole.ASSISTANT,
                    content=f"Lint complete: {len(result.issues)} issues found",
                    command="lint",
                )
            )
            await session.commit()

            await websocket.send_json(
                {
                    "type": "complete",
                    "message_id": str(uuid.uuid4()),
                    "result": {
                        "issues": [asdict(i) for i in result.issues],
                    },
                }
            )
        except HypatiaError as e:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": e.detail,
                    "code": e.code.value,
                    "user_action": e.user_action,
                }
            )
        except Exception as e:  # noqa: BLE001
            await websocket.send_json(
                {"type": "error", "message": str(e), "code": ErrorCode.LINT_ERROR}
            )


async def _handle_export(websocket: WebSocket, class_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        try:
            session.add(ChatMessage(class_id=class_id, role=ChatRole.USER, content="/export"))
            await session.commit()

            result = await wiki_engine.handle_export(session, class_id)
            if result.success:
                session.add(
                    ChatMessage(
                        class_id=class_id,
                        role=ChatRole.ASSISTANT,
                        content=f"Export complete: {result.page_count} pages",
                        command="export",
                    )
                )
                await session.commit()
                await websocket.send_json(
                    {
                        "type": "complete",
                        "message_id": str(uuid.uuid4()),
                        "result": {
                            "export_path": result.export_path,
                            "page_count": result.page_count,
                        },
                    }
                )
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": result.error or "Export failed",
                        "code": "EXPORT_ERROR",
                    }
                )
        except HypatiaError as e:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": e.detail,
                    "code": e.code.value,
                    "user_action": e.user_action,
                }
            )
        except Exception as e:  # noqa: BLE001
            await websocket.send_json(
                {"type": "error", "message": str(e), "code": ErrorCode.EXPORT_ERROR}
            )


async def _handle_rebuild(websocket: WebSocket, class_id: uuid.UUID) -> None:
    task_id = task_manager.start_task("rebuild", str(class_id))
    await websocket.send_json(
        {
            "type": "progress",
            "operation_id": task_id,
            "percent": 0,
            "message": "Starting rebuild...",
        }
    )

    async def _run() -> None:
        async with async_session_factory() as session:
            try:
                await wiki_engine.handle_rebuild(session, class_id, task_id=task_id)
                task_manager.complete_task(task_id)
            except (OSError, ValueError, RuntimeError, HypatiaError) as e:
                task_manager.fail_task(task_id, str(e))

    rebuild_task = asyncio.create_task(_run())

    try:
        while True:
            t = task_manager.get_status(task_id)
            if t is None:
                break
            if t.status == "complete":
                await websocket.send_json(
                    {
                        "type": "complete",
                        "message_id": str(uuid.uuid4()),
                        "result": {"task_id": task_id},
                    }
                )
                break
            elif t.status in ("failed", "cancelled"):
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": t.error or t.message,
                        "code": "REBUILD_ERROR",
                    }
                )
                break
            else:
                await websocket.send_json(
                    {
                        "type": "progress",
                        "operation_id": task_id,
                        "percent": t.progress,
                        "message": t.message,
                    }
                )
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        task_manager.cancel_task(task_id)
        raise
    finally:
        if not rebuild_task.done():
            rebuild_task.cancel()


@router.get("/history", response_model=list[ChatMessageRead])
async def get_chat_history(
    class_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[ChatMessageRead]:
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.class_id == class_id)
        .order_by(ChatMessage.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return [ChatMessageRead.model_validate(msg) for msg in result.scalars().all()]


@router.delete("/history", status_code=204)
async def clear_chat_history(
    class_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> None:
    await session.execute(delete(ChatMessage).where(ChatMessage.class_id == class_id))
    await session.commit()
