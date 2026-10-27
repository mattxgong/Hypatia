"""The backend exits when the desktop app's stdin pipe closes (HYPATIA_EXIT_ON_STDIN_CLOSE)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(port: int, proc: subprocess.Popen[bytes], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        assert proc.poll() is None, "backend exited before becoming healthy"
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
                return
        except OSError:
            time.sleep(0.25)
    raise AssertionError("backend never became healthy")


def test_backend_exits_when_stdin_closes(tmp_path: Path) -> None:
    port = _free_port()
    env = {
        **os.environ,
        "HYPATIA_DATA_DIR": str(tmp_path / "data"),
        "HYPATIA_LOGS_DIR": str(tmp_path / "logs"),
        "HYPATIA_EXIT_ON_STDIN_CLOSE": "1",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=BACKEND_DIR,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_health(port, proc, timeout=60)
        assert proc.stdin is not None
        proc.stdin.close()
        proc.wait(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
