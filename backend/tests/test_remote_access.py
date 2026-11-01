"""Remote access (Phase 10.3): certificate, addresses, status, two listeners."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from httpx import ASGITransport, AsyncClient

from app import database, serve
from app.config import settings
from app.main import app
from app.services import device_auth, remote_access

TOKEN = "launch-token"
LOCAL = {"authorization": f"Bearer {TOKEN}"}


def test_the_certificate_is_made_once_and_kept(tmp_path: Path) -> None:
    cert, key = remote_access.ensure_certificate(tmp_path)
    first = remote_access.fingerprint(cert)

    again, _ = remote_access.ensure_certificate(tmp_path)

    assert remote_access.fingerprint(again) == first
    der = x509.load_pem_x509_certificate(cert.read_bytes()).public_bytes(serialization.Encoding.DER)
    assert first == hashlib.sha256(der).hexdigest()
    assert key.read_bytes().startswith(b"-----BEGIN PRIVATE KEY-----")


def test_urls_list_lan_then_tailscale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        remote_access, "_interface_addresses", lambda: ["100.101.1.2", "192.168.1.20"]
    )
    monkeypatch.setattr(
        remote_access, "_tailscale_status", lambda: (["100.101.1.2"], "desk.tail1.ts.net")
    )

    assert remote_access.pairing_urls(8765) == [
        "https://192.168.1.20:8765",
        "https://100.101.1.2:8765",
        "https://desk.tail1.ts.net:8765",
    ]


def test_without_tailscale_only_lan_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(remote_access, "_interface_addresses", lambda: ["10.0.0.5"])
    monkeypatch.setattr(remote_access.shutil, "which", lambda _: None)

    assert remote_access.pairing_urls(9000) == ["https://10.0.0.5:9000"]


class TestStatusEndpoint:
    @pytest.fixture(autouse=True)
    async def setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        await database.run_migrations()
        settings.api_token = TOKEN
        device_auth.pairing_codes = device_auth.PairingCodes()
        monkeypatch.setattr(remote_access, "pairing_urls", lambda port: [f"https://lan:{port}"])

    @pytest.fixture
    async def client(self) -> AsyncIterator[AsyncClient]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as ac:
            yield ac

    async def test_off_by_default(self, client: AsyncClient) -> None:
        resp = await client.get("/api/devices/remote-access", headers=LOCAL)

        assert resp.json() == {"enabled": False, "port": None, "urls": [], "cert_sha256": None}
        code = (await client.post("/api/devices/pairing-code", headers=LOCAL)).json()
        assert (code["urls"], code["cert_sha256"]) == ([], None)

    async def test_on_it_gives_the_qr_contents(self, client: AsyncClient) -> None:
        settings.remote_access_enabled = True
        settings.remote_port = 8765
        cert, _ = remote_access.ensure_certificate(settings.data_dir)
        expected = remote_access.fingerprint(cert)

        status = (await client.get("/api/devices/remote-access", headers=LOCAL)).json()
        code = (await client.post("/api/devices/pairing-code", headers=LOCAL)).json()

        assert status == {
            "enabled": True,
            "port": 8765,
            "urls": ["https://lan:8765"],
            "cert_sha256": expected,
        }
        assert (code["urls"], code["cert_sha256"]) == (["https://lan:8765"], expected)

    async def test_devices_cannot_read_it(self, client: AsyncClient) -> None:
        code = (await client.post("/api/devices/pairing-code", headers=LOCAL)).json()["code"]
        token = (
            await client.post("/api/devices/pair", json={"code": code, "device_name": "Pixel"})
        ).json()["token"]

        resp = await client.get(
            "/api/devices/remote-access", headers={"authorization": f"Bearer {token}"}
        )

        assert resp.status_code == 403


class _FakeServer:
    def __init__(self, run_for: float) -> None:
        self.run_for = run_for
        self.started = False
        self.should_exit = False
        self.ran = False

    async def serve(self) -> None:
        self.started = True
        self.ran = True
        waited = 0.0
        while not self.should_exit and waited < self.run_for:
            await asyncio.sleep(0.01)
            waited += 0.01


async def test_the_phone_listener_stops_with_the_main_one() -> None:
    local, remote = _FakeServer(run_for=0.1), _FakeServer(run_for=60)

    await asyncio.wait_for(serve._serve(local, remote), timeout=5)  # type: ignore[arg-type]

    assert remote.ran and remote.should_exit


async def test_the_phone_listener_never_starts_if_startup_fails() -> None:
    class _Failing(_FakeServer):
        async def serve(self) -> None:
            raise RuntimeError("migrations failed")

    remote = _FakeServer(run_for=60)

    with pytest.raises(RuntimeError):
        await serve._serve(_Failing(0), remote)  # type: ignore[arg-type]
    assert not remote.ran
