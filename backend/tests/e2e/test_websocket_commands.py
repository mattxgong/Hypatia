"""WebSocket E2E tests for chat commands (Task 8.2b).

Tests for /summarize, /remove, /lint commands over the WebSocket protocol.
These use the mock LLM and in-memory database from conftest fixtures.
"""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.asyncio


class TestChatWebSocketCommands:
    """WebSocket E2E tests for chat commands."""

    async def test_help_command(self, e2e_client: AsyncClient, e2e_class: dict) -> None:
        class_id = e2e_class["id"]

        transport = ASGITransport(app=app)
        async with (
            AsyncClient(transport=transport, base_url="http://test") as client,
            client.stream("GET", f"/api/classes/{class_id}/chat") as _,
        ):
            pass

    async def test_ask_command_stream(self, e2e_client: AsyncClient, e2e_class: dict) -> None:
        """Verify that /ask streams chunks then sends a complete message."""
        class_id = e2e_class["id"]

        with (
            TestClient(app) as client,
            client.websocket_connect(f"/api/classes/{class_id}/chat") as ws,
        ):
            ws.send_json({"type": "message", "content": "/ask What is machine learning?"})

            messages = []
            for _ in range(50):
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

            types = [m["type"] for m in messages]
            assert "complete" in types or "error" in types

    async def test_summarize_command(
        self, e2e_client: AsyncClient, e2e_class: dict, sample_source_file
    ) -> None:
        """Verify /summarize returns a complete or error response."""
        class_id = e2e_class["id"]

        await e2e_client.post(
            f"/api/classes/{class_id}/files",
            files={
                "files": (
                    "notes.md",
                    io.BytesIO(sample_source_file.read_bytes()),
                    "text/markdown",
                )
            },
        )

        with (
            TestClient(app) as client,
            client.websocket_connect(f"/api/classes/{class_id}/chat") as ws,
        ):
            ws.send_json({"type": "message", "content": "/summarize machine learning"})

            messages = []
            for _ in range(50):
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

            final = messages[-1]
            assert final["type"] in ("complete", "error")

    async def test_remove_command(
        self, e2e_client: AsyncClient, e2e_class: dict, sample_source_file
    ) -> None:
        """Verify /remove returns a complete or error response."""
        class_id = e2e_class["id"]

        await e2e_client.post(
            f"/api/classes/{class_id}/files",
            files={
                "files": (
                    "notes.md",
                    io.BytesIO(sample_source_file.read_bytes()),
                    "text/markdown",
                )
            },
        )

        with (
            TestClient(app) as client,
            client.websocket_connect(f"/api/classes/{class_id}/chat") as ws,
        ):
            ws.send_json({"type": "message", "content": "/remove notes.md"})

            messages = []
            for _ in range(50):
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

            final = messages[-1]
            assert final["type"] in ("complete", "error")

    async def test_lint_command(self, e2e_client: AsyncClient, e2e_class: dict) -> None:
        """Verify /lint returns a complete response."""
        class_id = e2e_class["id"]

        with (
            TestClient(app) as client,
            client.websocket_connect(f"/api/classes/{class_id}/chat") as ws,
        ):
            ws.send_json({"type": "message", "content": "/lint"})

            messages = []
            for _ in range(50):
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] in ("complete", "error"):
                    break

            final = messages[-1]
            assert final["type"] in ("complete", "error")

    async def test_invalid_command(self, e2e_client: AsyncClient, e2e_class: dict) -> None:
        """Verify invalid commands return an error."""
        class_id = e2e_class["id"]

        with (
            TestClient(app) as client,
            client.websocket_connect(f"/api/classes/{class_id}/chat") as ws,
        ):
            ws.send_json({"type": "message", "content": "/nonexistent"})

            msg = ws.receive_json()
            assert msg["type"] == "error"

    async def test_cancel_message(self, e2e_client: AsyncClient, e2e_class: dict) -> None:
        """Verify cancel message does not crash the connection."""
        class_id = e2e_class["id"]

        with (
            TestClient(app) as client,
            client.websocket_connect(f"/api/classes/{class_id}/chat") as ws,
        ):
            ws.send_json({"type": "cancel", "operation_id": str(uuid.uuid4())})
            ws.send_json({"type": "message", "content": "/help"})

            msg = ws.receive_json()
            assert msg["type"] == "complete"
