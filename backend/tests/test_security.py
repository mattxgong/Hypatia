"""Tests for the local-access gate: Host, Origin and launch token (app/security.py)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.main import app

TOKEN = "launch-token"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as ac:
        yield ac


@pytest.fixture
def real_hosts() -> None:
    settings.allowed_hosts = ["127.0.0.1", "localhost", "::1"]


@pytest.mark.usefixtures("real_hosts")
class TestHost:
    @pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:8001", "[::1]:8000"])
    async def test_loopback_hosts_allowed(self, client: AsyncClient, host: str) -> None:
        resp = await client.get("/health", headers={"host": host})
        assert resp.status_code == 200

    async def test_rebinding_host_rejected(self, client: AsyncClient) -> None:
        resp = await client.get("/health", headers={"host": "attacker.example:8000"})
        assert resp.status_code == 400


class TestOrigin:
    async def test_foreign_origin_rejected(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/classes", json={"name": "x"}, headers={"origin": "https://evil.example"}
        )
        assert resp.status_code == 403

    async def test_localhost_origin_allowed(self, client: AsyncClient) -> None:
        resp = await client.get("/health", headers={"origin": "http://localhost:5173"})
        assert resp.status_code == 200


class TestToken:
    async def test_no_token_configured_allows_requests(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/tasks/{uuid.uuid4()}")
        assert resp.status_code != 401

    async def test_missing_or_wrong_token_rejected(self, client: AsyncClient) -> None:
        settings.api_token = TOKEN
        assert (await client.get("/api/tasks")).status_code == 401
        wrong = await client.get("/api/tasks", headers={"authorization": "Bearer nope"})
        assert wrong.status_code == 401

    async def test_correct_token_accepted(self, client: AsyncClient) -> None:
        settings.api_token = TOKEN
        resp = await client.get("/api/tasks", headers={"authorization": f"Bearer {TOKEN}"})
        assert resp.status_code == 200

    async def test_health_needs_no_token(self, client: AsyncClient) -> None:
        settings.api_token = TOKEN
        assert (await client.get("/health")).status_code == 200


class TestWebSocket:
    def test_foreign_origin_handshake_refused(self) -> None:
        url = f"/api/classes/{uuid.uuid4()}/chat"
        with (
            TestClient(app) as tc,
            pytest.raises(WebSocketDisconnect),
            tc.websocket_connect(url, headers={"origin": "https://evil.example"}),
        ):
            pass

    def test_missing_token_handshake_refused(self) -> None:
        settings.api_token = TOKEN
        with (
            TestClient(app) as tc,
            pytest.raises(WebSocketDisconnect),
            tc.websocket_connect(f"/api/classes/{uuid.uuid4()}/chat"),
        ):
            pass

    def test_token_header_handshake_accepted(self) -> None:
        settings.api_token = TOKEN
        with (
            TestClient(app) as tc,
            tc.websocket_connect(
                f"/api/classes/{uuid.uuid4()}/chat",
                headers={"authorization": f"Bearer {TOKEN}"},
            ),
        ):
            pass
