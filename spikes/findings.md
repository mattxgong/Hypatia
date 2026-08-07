# Phase 0.5: Technical Spike Findings

**Date**: 2026-08-06  
**Status**: In progress — Spike 0.5.2 ready to run, 0.5.1 blocked on model download, 0.5.3 needs interactive test

---

## Spike 0.5.1: faster-whisper Integration

### Setup
- Script: `spikes/faster_whisper_test.py`
- Model: `base` (fastest, ~74M parameters)
- Device: CPU only (`compute_type=int8` for efficiency)
- Dependencies: `faster-whisper`, `psutil`, `ffmpeg` (system)

### How to Run
```bash
cd spikes
pip install -r requirements.txt

# If HuggingFace is accessible:
python faster_whisper_test.py KT.mp4

# If HuggingFace is blocked (SSL handshake failure):
# 1. On an unrestricted network, download the model:
#    pip install huggingface_hub
#    python -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-base', local_dir='./faster-whisper-base')"
# 2. Copy the folder here, then:
python faster_whisper_test.py KT.mp4 --model-path ./faster-whisper-base
```

### What the Script Validates
1. ffmpeg audio extraction from video → WAV (16kHz mono)
2. faster-whisper model loading and transcription
3. Timestamped segment output
4. Performance metrics: real-time factor (RTF), memory usage
5. Markdown generation with timestamps

### First Run Attempt
- **Audio extraction**: PASS — ffmpeg extracted 300.8s of audio from KT.mp4
- **Model download**: BLOCKED — HuggingFace is blocked at the network level (SSL handshake failure)
- **Error**: `SSLV3_ALERT_HANDSHAKE_FAILURE` when attempting to download model from `huggingface.co`
- **Workaround added**: `--model-path` flag to use a pre-downloaded CTranslate2 model directory

### Results
*Blocked — needs model downloaded from unrestricted network*

| Metric | Value |
|--------|-------|
| Audio duration | 300.8 s |
| Transcription time | *pending* |
| Real-time factor | *pending* |
| Memory delta | *pending* |
| Segments produced | *pending* |
| Language detected | *pending* |

### Go/No-go
- **Criteria**: RTF < 2.0x on CPU
- **Result**: PENDING (blocked on model download)

### Key Finding
HuggingFace is blocked by the enterprise network firewall. The `--model-path` workaround allows offline usage, which is also good for production: we should ship or cache the model locally rather than downloading it on first use.

---

## Spike 0.5.2: LLM Structured Output Parsing

### Setup
- Script: `spikes/llm_parsing_test.py`
- Provider: GitHub Copilot (via device code OAuth + session token exchange)
- Model: `gpt-4o`
- Endpoint: `https://api.individual.githubcopilot.com`
- Auth: Device code OAuth flow (same as VS Code Copilot extension)

### How to Run
```bash
cd spikes
pip install -r requirements.txt

# First run will prompt for device code authorization:
#   1. Open https://github.com/login/device
#   2. Enter the displayed code
#   Token is cached in .copilot_token for subsequent runs
python llm_parsing_test.py --runs 10
```

### Auth Discovery
The original PAT-based approach failed:
- PAT has `copilot, read:enterprise` scopes
- **GitHub Models API** (`models.inference.ai.azure.com`): Returns 404. Needs `models:read` scope which the PAT doesn't have.
- **Copilot completions API** (`api.individual.githubcopilot.com`): Returns HTTP 400 "Personal Access Tokens are not supported for this endpoint"
- **Copilot token exchange** (`api.github.com/copilot_internal/v2/token`): Returns 404 with a PAT

**Solution**: Implemented the device code OAuth flow (same flow VS Code's Copilot extension uses). The flow:
1. Request a device code from `github.com/login/device/code` using Copilot's OAuth client ID
2. User authorizes in browser
3. Exchange device code for OAuth access token
4. Exchange OAuth token for Copilot session token via `api.github.com/copilot_internal/v2/token`
5. Use session token to call `api.individual.githubcopilot.com/chat/completions`

### What the Script Validates
1. LLM can produce multiple XML-tagged wiki pages from a source document
2. XML tags can be reliably parsed with regex
3. YAML frontmatter within pages is well-formed
4. Cross-references between pages are present
5. Consistency across multiple runs (10 by default)

### XML Format Tested
```xml
<wiki-page path="pages/concepts/example.md">
---
title: "Example Concept"
source: "source-file.md"
tags: [tag1, tag2]
---
Content with [[cross-references]]...
</wiki-page>
```

### Results
*Pending — needs interactive device code authorization*

| Metric | Value |
|--------|-------|
| Success rate | ___/10 (___%) |
| Avg pages per run | ___ |
| Avg response time | ___ s |
| Avg output length | ___ chars |
| Parse failures | ___ |

### Go/No-go
- **Criteria**: Parse success rate > 90%
- **Result**: PENDING (needs OAuth authorization)

### Architectural Insight
PATs cannot access the Copilot inference API. The production app will need to implement the device code OAuth flow or use a different auth mechanism. This is important for the backend's LLM integration design.

---

## Spike 0.5.3: Flutter Subprocess Management

### Setup
- App: `spikes/flutter_subprocess/`
- Backend: `spikes/flutter_subprocess/backend/server.py` (FastAPI + uvicorn)
- Platform: Windows (primary target)

### How to Run
```bash
cd spikes/flutter_subprocess
pip install fastapi uvicorn  # for the backend
flutter run -d windows
```

### What the App Validates
1. **Python discovery**: Tries `python`, `python3`, `py` commands, then common Windows install paths
2. **Port conflict detection**: Checks if port 8742 is available, increments if not
3. **Process spawning**: Starts uvicorn as a child process with captured stdout/stderr
4. **Health check polling**: Polls `GET /health` every 1s until backend responds, then every 5s
5. **Status display**: Shows starting → ready → error transitions in UI
6. **Graceful shutdown**: Uses `taskkill /F /T /PID` on Windows to kill entire process tree
7. **Lifecycle management**: Kills backend in `dispose()` when app closes

### Results
*Needs interactive `flutter run -d windows`*

| Test | Pass/Fail |
|------|-----------|
| Python discovered automatically | ___ |
| Backend starts successfully | ___ |
| Health check detects readiness | ___ |
| UI shows status transitions | ___ |
| Backend stops on "Stop" button | ___ |
| No orphan processes after app close | ___ |
| Port conflict recovery works | ___ |

### Go/No-go
- **Criteria**: Subprocess reliably starts/stops, health check works, no orphans
- **Result**: PENDING (needs interactive test)

### Platform Notes (Windows)
- `Process.run('python', ...)` works if Python is on PATH
- `taskkill /F /T /PID <pid>` kills the process tree (uvicorn + worker processes)
- Port binding test uses `ServerSocket.bind` to check availability before spawning
- The `py` launcher (Python Launcher for Windows) is the most reliable discovery method

---

## Summary

### Current Status
| Spike | Code | Blocker | Action Required |
|-------|------|---------|-----------------|
| 0.5.1 faster-whisper | Done | HuggingFace blocked by firewall | Download model from unrestricted network, use `--model-path` |
| 0.5.2 LLM parsing | Done | Needs OAuth authorization | Run `python llm_parsing_test.py` and authorize in browser |
| 0.5.3 Flutter subprocess | Done | Needs interactive test | Run `flutter run -d windows` |

### Key Findings So Far

1. **Enterprise network blocks HuggingFace**: The whisper model can't be auto-downloaded. Production design should bundle or cache models locally rather than relying on runtime downloads.

2. **Copilot API requires OAuth, not PATs**: Personal Access Tokens cannot access the Copilot inference API. The production backend must implement the device code OAuth flow (or the app must mediate auth through the desktop client). This is a significant architectural finding.

3. **Flutter subprocess code is complete**: The spike implements all required functionality including Python discovery, port conflict detection, process tree kill, and health checking. Just needs the interactive validation run.

### Next Steps
1. Download faster-whisper model from unrestricted network → re-run spike 0.5.1
2. Run `python llm_parsing_test.py` → authorize in browser → validate spike 0.5.2
3. Run `flutter run -d windows` → manually test subprocess lifecycle → validate spike 0.5.3
4. Update this document with actual results and make go/no-go decisions
