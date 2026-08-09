#!/usr/bin/env bash
# Starts the backend (uvicorn) and frontend (flutter run) together for local dev.
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

if [ -f "$BACKEND_DIR/.venv/Scripts/python.exe" ]; then
  VENV_PY="$BACKEND_DIR/.venv/Scripts/python.exe"
else
  VENV_PY="$BACKEND_DIR/.venv/bin/python"
fi

if [ ! -f "$VENV_PY" ]; then
  echo "Backend venv not found at $BACKEND_DIR/.venv. Run scripts/setup.sh first." >&2
  exit 1
fi

echo "==> Starting backend (uvicorn) on http://127.0.0.1:8000"
(cd "$BACKEND_DIR" && "$VENV_PY" -m uvicorn app.main:app --reload --port 8000) &
BACKEND_PID=$!

cleanup() {
  echo "==> Stopping backend (pid $BACKEND_PID)"
  kill "$BACKEND_PID" >/dev/null 2>&1 || true
  wait "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> Starting frontend (flutter run)"
(cd "$FRONTEND_DIR" && flutter run)
