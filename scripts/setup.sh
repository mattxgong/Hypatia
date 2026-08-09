#!/usr/bin/env bash
# Sets up a fresh clone for local development: backend venv + deps, frontend deps.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

echo "==> Setting up Hypatia dev environment"

# --- Backend: Python venv + dependencies ------------------------------------
if [ ! -d "$BACKEND_DIR/.venv" ]; then
  echo "==> Creating Python venv in backend/.venv"
  if command -v python3 >/dev/null 2>&1; then
    python3 -m venv "$BACKEND_DIR/.venv"
  else
    python -m venv "$BACKEND_DIR/.venv"
  fi
fi

if [ -f "$BACKEND_DIR/.venv/Scripts/python.exe" ]; then
  VENV_PY="$BACKEND_DIR/.venv/Scripts/python.exe"
else
  VENV_PY="$BACKEND_DIR/.venv/bin/python"
fi

echo "==> Installing backend dependencies (pip install -e .[dev])"
"$VENV_PY" -m pip install --upgrade pip
(cd "$BACKEND_DIR" && "$VENV_PY" -m pip install -e ".[dev]")

# --- Frontend: Flutter dependencies ------------------------------------------
echo "==> Running flutter pub get"
(cd "$FRONTEND_DIR" && flutter pub get)

cat <<'NOTE'

==> ffmpeg requirement
Hypatia's backend uses ffmpeg to convert/transcode audio and video source
files. Install it and make sure it is on your PATH:
  macOS:           brew install ffmpeg
  Ubuntu/Debian:   sudo apt install ffmpeg
  Windows:         winget install ffmpeg  (or see https://ffmpeg.org/download.html)

==> Setup complete. Run scripts/run_dev.sh to start the dev servers.
NOTE
