"""Device pairing and device tokens (app/routers/devices.py, app/security.py)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from app import database
from app.config import settings
from app.main import app
from app.services import device_auth

LAUNCH_TOKEN = "launch-token"
LOCAL = {"authorization": f"Bearer {LAUNCH_TOKEN}"}


@pytest.fixture(autouse=True)
async def schema() -> None:
    await database.run_migrations()
    settings.api_token = LAUNCH_TOKEN
    device_auth.pairing_codes = device_auth.PairingCodes()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, client=("192.168.1.20", 50000))
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as ac:
        yield ac


async def _issue_code(client: AsyncClient) -> str:
    resp = await client.post("/api/devices/pairing-code", headers=LOCAL)
    assert resp.status_code == 200
    return resp.json()["code"]


async def _pair(client: AsyncClient, name: str = "Pixel") -> dict:
    code = await _issue_code(client)
    resp = await client.post("/api/devices/pair", json={"code": code, "device_name": name})
    assert resp.status_code == 201
    return resp.json()


def _bearer(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


async def test_a_paired_device_can_use_the_api(client: AsyncClient) -> None:
    paired = await _pair(client)

    resp = await client.get("/api/devices", headers=_bearer(paired["token"]))

    assert resp.status_code == 200
    [device] = resp.json()
    assert device["id"] == paired["device"]["id"]
    assert device["name"] == "Pixel"
    assert device["last_seen_ip"] == "192.168.1.20"
    assert device["last_seen_at"] is not None
    assert "token" not in device and "token_hash" not in device


async def test_only_the_token_hash_is_stored(client: AsyncClient) -> None:
    paired = await _pair(client)

    async with database.async_session_factory() as session:
        device = await session.get(device_auth.Device, uuid.UUID(paired["device"]["id"]))

    assert device is not None
    assert device.token_hash == device_auth.hash_token(paired["token"])
    assert paired["token"] not in device.token_hash


async def test_codes_ignore_case_spaces_and_dashes(client: AsyncClient) -> None:
    code = await _issue_code(client)
    typed = f"{code[:4].lower()}-{code[4:]} "

    resp = await client.post("/api/devices/pair", json={"code": typed, "device_name": "iPad"})

    assert resp.status_code == 201


async def test_a_code_works_once(client: AsyncClient) -> None:
    code = await _issue_code(client)
    body = {"code": code, "device_name": "Pixel"}
    assert (await client.post("/api/devices/pair", json=body)).status_code == 201

    again = await client.post("/api/devices/pair", json=body)

    assert again.status_code == 400
    assert again.json()["code"] == "PAIRING_CODE_INVALID"


async def test_wrong_guesses_wear_out_the_code(client: AsyncClient) -> None:
    code = await _issue_code(client)
    for _ in range(5):
        wrong = await client.post("/api/devices/pair", json={"code": "WRONG", "device_name": "x"})
        assert wrong.status_code == 400

    resp = await client.post("/api/devices/pair", json={"code": code, "device_name": "x"})

    assert resp.status_code == 400


async def test_an_expired_code_fails(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    code = await _issue_code(client)
    later = device_auth.time.monotonic() + device_auth.PAIRING_CODE_TTL_SECONDS + 1
    monkeypatch.setattr(device_auth.time, "monotonic", lambda: later)

    resp = await client.post("/api/devices/pair", json={"code": code, "device_name": "x"})

    assert resp.status_code == 400


async def test_a_new_code_replaces_the_old_one(client: AsyncClient) -> None:
    old = await _issue_code(client)
    await _issue_code(client)

    resp = await client.post("/api/devices/pair", json={"code": old, "device_name": "x"})

    assert resp.status_code == 400


async def test_a_device_cannot_offer_pairing_codes(client: AsyncClient) -> None:
    paired = await _pair(client)

    resp = await client.post("/api/devices/pairing-code", headers=_bearer(paired["token"]))

    assert resp.status_code == 403
    assert resp.json()["code"] == "LOCAL_CLIENT_REQUIRED"


async def test_a_revoked_device_is_refused(client: AsyncClient) -> None:
    paired = await _pair(client)
    device_id = paired["device"]["id"]

    assert (await client.delete(f"/api/devices/{device_id}", headers=LOCAL)).status_code == 204

    resp = await client.get("/api/devices", headers=_bearer(paired["token"]))
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_INVALID"
    assert resp.json()["user_action"]
    assert (await client.get("/api/devices", headers=LOCAL)).json() == []
    again = await client.delete(f"/api/devices/{device_id}", headers=LOCAL)
    assert again.status_code == 404


async def test_a_device_can_revoke_itself(client: AsyncClient) -> None:
    paired = await _pair(client)
    headers = _bearer(paired["token"])

    resp = await client.delete(f"/api/devices/{paired['device']['id']}", headers=headers)

    assert resp.status_code == 204
    assert (await client.get("/api/devices", headers=headers)).status_code == 401


async def test_no_token_is_auth_required(client: AsyncClient) -> None:
    resp = await client.get("/api/devices")

    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_REQUIRED"


async def test_pairing_needs_no_token_but_offering_a_code_does(client: AsyncClient) -> None:
    assert (await client.post("/api/devices/pairing-code")).status_code == 401
    resp = await client.post("/api/devices/pair", json={"code": "ABCDEFGH", "device_name": "x"})
    assert resp.json()["code"] == "PAIRING_CODE_INVALID"


async def test_device_token_opens_the_chat_socket(client: AsyncClient) -> None:
    paired = await _pair(client)

    with (
        TestClient(app) as tc,
        tc.websocket_connect(f"/api/classes/{uuid.uuid4()}/chat", headers=_bearer(paired["token"])),
    ):
        pass
