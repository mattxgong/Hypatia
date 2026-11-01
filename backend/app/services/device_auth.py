"""Device pairing and token checks for remote access (Phase 10).

A phone pairs by redeeming a short-lived code shown on the desktop, and gets a
random token once. Only the token's SHA-256 is stored, so a copy of the
database can't be used to sign in.
"""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import database
from app.models.db_models import Device

PAIRING_CODE_TTL_SECONDS = 300
# Wrong guesses allowed before the code stops working. With 8 characters from
# a 31-letter alphabet, guessing it in this many tries is out of reach.
_MAX_PAIRING_ATTEMPTS = 5
# Easy to read aloud and type: no 0/O or 1/I/L.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 8
# Don't write to the database on every request just to move last_seen_at.
_LAST_SEEN_INTERVAL = timedelta(minutes=1)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_code(code: str) -> str:
    return "".join(code.split()).replace("-", "").upper()


@dataclass
class _PairingCode:
    code: str
    expires_at: float
    attempts_left: int = _MAX_PAIRING_ATTEMPTS


class PairingCodes:
    """The one pairing code currently on offer. A new code replaces the old one."""

    def __init__(self) -> None:
        self._current: _PairingCode | None = None

    def issue(self) -> tuple[str, datetime]:
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        self._current = _PairingCode(code, time.monotonic() + PAIRING_CODE_TTL_SECONDS)
        return code, datetime.now(UTC) + timedelta(seconds=PAIRING_CODE_TTL_SECONDS)

    def redeem(self, code: str) -> bool:
        """Use up the code if it matches. Wrong guesses wear it out."""
        current = self._current
        if current is None or time.monotonic() > current.expires_at:
            self._current = None
            return False
        if secrets.compare_digest(normalize_code(code).encode(), current.code.encode()):
            self._current = None
            return True
        current.attempts_left -= 1
        if current.attempts_left <= 0:
            self._current = None
        return False


pairing_codes = PairingCodes()


async def create_device(session: AsyncSession, name: str) -> tuple[Device, str]:
    """Add a device and return it with its token, which is never shown again."""
    token = secrets.token_urlsafe(32)
    device = Device(name=name, token_hash=hash_token(token))
    session.add(device)
    await session.commit()
    await session.refresh(device)
    return device, token


async def authenticate(token: str, client_ip: str | None) -> uuid.UUID | None:
    """The ID of the unrevoked device that owns the token, or None."""
    async with database.async_session_factory() as session:
        device = await session.scalar(
            select(Device).where(
                Device.token_hash == hash_token(token), Device.revoked_at.is_(None)
            )
        )
        if device is None:
            return None
        now = datetime.now(UTC)
        if (
            device.last_seen_at is None
            or now - device.last_seen_at >= _LAST_SEEN_INTERVAL
            or device.last_seen_ip != client_ip
        ):
            device.last_seen_at = now
            device.last_seen_ip = client_ip
            await session.commit()
        return device.id
