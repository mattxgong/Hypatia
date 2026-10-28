"""Secure credential storage using keyring with encrypted file fallback.

The platform keyring is the real protection and is used whenever one exists.
Without one (CI, headless Linux), credentials go to ``.credentials`` in the
data directory, encrypted with a random key kept beside it in
``.credentials.key``. Both files are readable by the owner only, which is
what protects them; the encryption keeps the secrets out of casual view (and
out of backups of the file alone).

Older versions derived the key from the hostname, username and home folder;
such a file is decrypted with that key and re-encrypted with a random one.
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import json
import os
import platform
import stat
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from app.utils.logging import get_logger

logger = get_logger()

_SERVICE_NAME = "hypatia"
_FALLBACK_FILENAME = ".credentials"
_KEY_FILENAME = ".credentials.key"


def _current_user() -> str:
    # os.getlogin() raises without a controlling terminal (a GUI-launched backend).
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return ""


def _legacy_machine_keys() -> list[bytes]:
    """Keys older versions derived from machine identifiers, newest guess first."""
    users = {_current_user()}
    try:
        users.add(os.getlogin())
    except OSError:
        pass
    keys = []
    for user in users:
        seed = "|".join([platform.node(), user, str(Path.home())]).encode()
        keys.append(base64.urlsafe_b64encode(hashlib.sha256(seed).digest()))
    return keys


def _write_private(path: Path, data: bytes) -> None:
    """Atomically write ``data`` to ``path``, readable by the owner only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        if sys.platform != "win32":
            os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp_path, str(path))


class CredentialStore:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._keyring_available: bool | None = None
        self._fernet: object | None = None

    def _get_fernet(self):
        if self._fernet is None:
            from cryptography.fernet import Fernet

            self._fernet = Fernet(self._load_or_create_key())
        return self._fernet

    def _load_or_create_key(self) -> bytes:
        key_path = self._data_dir / _KEY_FILENAME
        if key_path.exists():
            return key_path.read_bytes().strip()
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        _write_private(key_path, key)
        return key

    def _check_keyring(self) -> bool:
        if self._keyring_available is not None:
            return self._keyring_available
        try:
            import keyring
            from keyring.errors import NoKeyringError

            keyring.get_password(_SERVICE_NAME, "__probe__")
            self._keyring_available = True
        except (NoKeyringError, RuntimeError, Exception):  # noqa: BLE001
            logger.info("keyring_unavailable", fallback="encrypted file")
            self._keyring_available = False
        return self._keyring_available

    def get(self, key: str) -> str | None:
        if self._check_keyring():
            import keyring

            return keyring.get_password(_SERVICE_NAME, key)
        return self._file_get(key)

    def set(self, key: str, value: str) -> None:
        if self._check_keyring():
            import keyring

            keyring.set_password(_SERVICE_NAME, key, value)
            return
        self._file_set(key, value)

    def delete(self, key: str) -> None:
        if self._check_keyring():
            import keyring

            try:
                keyring.delete_password(_SERVICE_NAME, key)
            except keyring.errors.PasswordDeleteError:
                pass
            return
        self._file_delete(key)

    def _fallback_path(self) -> Path:
        return self._data_dir / _FALLBACK_FILENAME

    def _load_file(self) -> dict[str, str]:
        path = self._fallback_path()
        if not path.exists():
            return {}
        raw = path.read_bytes()

        data = self._decrypt(raw)
        if data is None:
            data = self._read_legacy(raw)
            if data is None:
                self._set_aside_unreadable(path)
                return {}
            logger.info("credential_store_migrating", reason="re-encrypting with a random key")
            self._save_file(data)
        return data

    def _decrypt(self, raw: bytes) -> dict[str, str] | None:
        from cryptography.fernet import InvalidToken

        try:
            data = json.loads(self._get_fernet().decrypt(raw))  # type: ignore[attr-defined]
        except (InvalidToken, ValueError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _read_legacy(raw: bytes) -> dict[str, str] | None:
        """A file from an older version: machine-derived key, or plain JSON."""
        from cryptography.fernet import Fernet, InvalidToken

        for key in _legacy_machine_keys():
            try:
                data = json.loads(Fernet(key).decrypt(raw))
            except (InvalidToken, ValueError):
                continue
            if isinstance(data, dict):
                return data
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _set_aside_unreadable(path: Path) -> None:
        """Keep a file we can't decrypt instead of letting the next save replace it."""
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        backup = path.with_name(f"{path.name}.unreadable-{stamp}.bak")
        try:
            path.replace(backup)
        except OSError:
            logger.exception("credential_store_unreadable", path=str(path))
            return
        logger.error(
            "credential_store_unreadable",
            path=str(path),
            moved_to=str(backup),
            detail="saved API keys could not be decrypted; enter them again in Settings",
        )

    def _save_file(self, data: dict[str, str]) -> None:
        encrypted = self._get_fernet().encrypt(json.dumps(data).encode())  # type: ignore[attr-defined]
        _write_private(self._fallback_path(), encrypted)

    def _file_get(self, key: str) -> str | None:
        return self._load_file().get(key)

    def _file_set(self, key: str, value: str) -> None:
        data = self._load_file()
        data[key] = value
        self._save_file(data)

    def _file_delete(self, key: str) -> None:
        data = self._load_file()
        data.pop(key, None)
        self._save_file(data)
