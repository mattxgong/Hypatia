"""Secure credential storage using keyring with encrypted file fallback."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import stat
import tempfile
from pathlib import Path

from app.utils.logging import get_logger

logger = get_logger()

_SERVICE_NAME = "hypatia"
_FALLBACK_FILENAME = ".credentials"


def _derive_machine_key() -> bytes:
    """Derive a Fernet key from stable machine-specific identifiers."""
    parts = [
        platform.node(),
        os.getlogin() if hasattr(os, "getlogin") else "",
        str(Path.home()),
    ]
    seed = "|".join(parts).encode()
    digest = hashlib.sha256(seed).digest()
    return base64.urlsafe_b64encode(digest)


class CredentialStore:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._keyring_available: bool | None = None
        self._fernet: object | None = None

    def _get_fernet(self):
        if self._fernet is None:
            from cryptography.fernet import Fernet

            self._fernet = Fernet(_derive_machine_key())
        return self._fernet

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
        try:
            raw = path.read_bytes()
            fernet = self._get_fernet()
            decrypted = fernet.decrypt(raw)
            data = json.loads(decrypted)
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            try:
                text = path.read_text(encoding="utf-8")
                data = json.loads(text)
                if isinstance(data, dict):
                    logger.info("credential_store_migrating", reason="plaintext to encrypted")
                    self._save_file(data)
                    return data
            except (json.JSONDecodeError, OSError):
                pass
            return {}

    def _save_file(self, data: dict[str, str]) -> None:
        path = self._fallback_path()
        fernet = self._get_fernet()
        encrypted = fernet.encrypt(json.dumps(data).encode())
        try:
            fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
            try:
                os.write(fd, encrypted)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp_path, str(path))
            if os.name != "nt":
                path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            path.write_bytes(encrypted)
            if os.name != "nt":
                try:
                    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
                except OSError:
                    pass

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
