"""Encrypted-file fallback of the credential store (used when no keyring exists)."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.services import credential_store
from app.services.credential_store import CredentialStore


def _file_store(data_dir: Path) -> CredentialStore:
    store = CredentialStore(data_dir)
    store._keyring_available = False
    return store


def test_round_trip_uses_a_random_key_file(tmp_path: Path):
    store = _file_store(tmp_path)
    store.set("anthropic_api_key", "sk-secret")

    assert _file_store(tmp_path).get("anthropic_api_key") == "sk-secret"
    key = (tmp_path / ".credentials.key").read_bytes()
    assert key not in credential_store._legacy_machine_keys()
    assert b"sk-secret" not in (tmp_path / ".credentials").read_bytes()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_files_are_owner_only(tmp_path: Path):
    _file_store(tmp_path).set("github_token", "ghp_x")
    for name in (".credentials", ".credentials.key"):
        mode = stat.S_IMODE(os.stat(tmp_path / name).st_mode)
        assert mode == stat.S_IRUSR | stat.S_IWUSR


def test_file_from_an_older_version_is_migrated(tmp_path: Path):
    legacy_key = credential_store._legacy_machine_keys()[0]
    payload = json.dumps({"openai_api_key": "sk-old"}).encode()
    (tmp_path / ".credentials").write_bytes(Fernet(legacy_key).encrypt(payload))

    assert _file_store(tmp_path).get("openai_api_key") == "sk-old"
    new_key = (tmp_path / ".credentials.key").read_bytes()
    decrypted = Fernet(new_key).decrypt((tmp_path / ".credentials").read_bytes())
    assert json.loads(decrypted) == {"openai_api_key": "sk-old"}


def test_plaintext_file_is_migrated(tmp_path: Path):
    (tmp_path / ".credentials").write_text(json.dumps({"github_token": "ghp_plain"}))
    assert _file_store(tmp_path).get("github_token") == "ghp_plain"
    assert b"ghp_plain" not in (tmp_path / ".credentials").read_bytes()


def test_unreadable_file_is_set_aside_not_overwritten(tmp_path: Path):
    original = Fernet(Fernet.generate_key()).encrypt(b'{"anthropic_api_key": "sk-lost"}')
    (tmp_path / ".credentials").write_bytes(original)
    store = _file_store(tmp_path)

    assert store.get("anthropic_api_key") is None
    store.set("anthropic_api_key", "sk-new")

    [backup] = tmp_path.glob(".credentials.unreadable-*.bak")
    assert backup.read_bytes() == original
    assert _file_store(tmp_path).get("anthropic_api_key") == "sk-new"


def test_current_user_never_raises(monkeypatch: pytest.MonkeyPatch):
    def no_user() -> str:
        raise OSError("no controlling terminal")

    monkeypatch.setattr(credential_store.getpass, "getuser", no_user)
    monkeypatch.setattr(credential_store.os, "getlogin", no_user)
    assert credential_store._current_user() == ""
    assert credential_store._legacy_machine_keys()
