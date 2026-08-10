<h1 align="center">Hypatia</h1>

<p align="center">
  <a href="https://github.com/mattxgong/Hypatia/actions/workflows/ci.yml"><img src="https://github.com/mattxgong/Hypatia/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

<p align="center">
  <strong>A cross-platform Flutter application with a FastAPI Python backend that allows users to create a class, which contains its own wiki and repository of information that you can use to study. Populate it by uploading lecture videos, notes, and other study materials.</strong>
</p>

## Quickstart

First-time setup (creates the backend venv + deps, and runs `flutter pub get`):

```bash
scripts/setup.sh
```

This also reminds you to install `ffmpeg`, which the backend needs for
audio/video conversion.

Run both the backend and frontend for local development:

```bash
scripts/run_dev.sh
```

See [`CLAUDE.md`](CLAUDE.md) for the full repository layout, architecture
overview, and coding/testing conventions, and [`docs/plan/`](docs/plan/) for
the phase-by-phase implementation plans.