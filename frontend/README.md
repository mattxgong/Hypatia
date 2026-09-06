---
title: Hypatia Frontend Development
description: Build, run, test, and package the Flutter desktop client for Hypatia
---

## Overview

The frontend is a Flutter desktop application for Windows, macOS, and Linux.
It uses Riverpod for state, Dio for HTTP requests, and WebSocket connections
for streaming chat. The desktop entry point also manages the local FastAPI
backend process.

## Prerequisites

* Flutter on the stable channel with the target desktop toolchain enabled
* Python 3.11 or newer for the backend launcher
* Git for wiki version history
* ffmpeg for audio and video processing

Run `flutter doctor` to verify the Flutter and platform build dependencies.
See the [root README](../README.md) for complete backend and provider setup.

## Install Dependencies

From this directory:

```bash
flutter pub get
```

The root `scripts/setup.sh` command prepares both the backend and frontend on
macOS and Linux. The root README provides equivalent Windows PowerShell steps.

## Run the Desktop App

Enable the desktop target once, then run the matching device:

```powershell
flutter config --enable-windows-desktop
flutter run -d windows
```

```bash
flutter config --enable-macos-desktop
flutter run -d macos
```

```bash
flutter config --enable-linux-desktop
flutter run -d linux
```

At startup, the app searches the repository or packaged artifact for a
neighboring `backend/` directory. It finds an installed Python 3.11 or newer,
creates `backend/.venv` when needed, installs backend requirements if FastAPI
is unavailable, selects a port from 8000 through 8010, and starts Uvicorn.

The startup screen provides retry, Python selection, copied diagnostics, and
troubleshooting actions when backend startup fails. Closing the desktop app
stops its backend process.

## Project Layout

* `lib/main.dart`: Desktop initialization and backend startup gate
* `lib/app.dart`: Routing and application shell
* `lib/models/`: API and UI data models
* `lib/providers/`: Riverpod state and workflow providers
* `lib/screens/`: Full-screen application views
* `lib/services/`: HTTP, WebSocket, and backend process clients
* `lib/widgets/`: Chat, sidebar, source viewer, wiki viewer, and shared widgets
* `test/`: Unit and widget tests
* `integration_test/`: Desktop workflow coverage

## Quality Checks

Run these commands from `frontend/`:

```bash
flutter analyze
dart format --set-exit-if-changed .
flutter test
flutter test integration_test/app_test.dart
```

## Build and Package

Create a local platform build with one of these commands:

```bash
flutter build windows
flutter build macos
flutter build linux
```

A raw local Flutter build does not copy the backend into its output. The
[manual release workflow](../.github/workflows/manual.yml) builds each desktop
target and adds `app/`, `alembic/`, `alembic.ini`, `pyproject.toml`,
`requirements.txt`, and `requirements.lock` under an adjacent `backend/`
directory before uploading the artifact.

Keep that artifact layout intact. The packaged launcher depends on the
adjacent backend directory and a Python 3.11 or newer installation on the
user's machine; Python, Ollama, models, Git, and ffmpeg are not bundled.
