# Troubleshooting

Common issues and solutions when running Hypatia.

---

## ffmpeg not found

**Symptom**: Video/audio uploads fail with "ffmpeg not found" or files stay in "processing" status indefinitely.

**Solution**: Install ffmpeg and make sure it's on your PATH.

- **Windows**: `winget install ffmpeg` or download from [ffmpeg.org](https://ffmpeg.org/download.html) and add the `bin/` directory to your system PATH.
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg` (Ubuntu/Debian) or `sudo dnf install ffmpeg` (Fedora)

Verify with `ffmpeg -version`. Restart the backend after installing.

---

## Upload rejected because a file already exists

**Symptom**: Uploading a file fails with "A file named ... already exists in this class."

**Solution**: File names are unique within a Class. Rename the file before uploading it, or remove the existing source first (for example with `/remove <filename>` in chat). Other files in the same upload are not stored, so upload them again after resolving the conflict.

---

## Desktop app reinstalls backend dependencies after an update

**Symptom**: After installing a newer build, the first launch shows "Installing backend dependencies from requirements.lock".

**Cause**: The app reinstalls whenever the packaged `backend/requirements.lock` differs from the lock it last installed into its Python environment. That environment is `backend-venv` in the app's per-user support directory, or `backend/.venv` in a development checkout. This keeps the environment matched to the build. The install requires network access; if it fails, check your connection and relaunch.

---

## LLM API key invalid or expired

**Symptom**: Chat commands return errors like "Authentication failed" or "Invalid API key". The error response includes `code: "LLM_AUTH_FAILED"`.

**Solution**:

1. Open **Settings** (gear icon in the sidebar).
2. Select your LLM provider and re-enter your API key.
3. The app validates the key on entry — look for a green check or error message.

If using environment variables, check your `backend/.env` file:

```bash
# Anthropic
HYPATIA_ANTHROPIC_API_KEY=sk-ant-api03-...

# OpenAI
HYPATIA_OPENAI_API_KEY=sk-...
```

Restart the backend after changing `.env` values.

---

## Port 8000 already in use

**Symptom**: Backend fails to start with `[Errno 10048]` (Windows) or `[Errno 98] Address already in use` (Linux/macOS).

**Solution**: Another process is using port 8000. Either stop the other process or change the port.

Find the conflicting process:

```bash
# Windows
netstat -ano | findstr :8000

# macOS/Linux
lsof -i :8000
```

To use a different port, start the backend manually:

```bash
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8001   # Windows
.venv/bin/python -m uvicorn app.main:app --port 8001            # macOS/Linux
```

Note: the Flutter app's `BackendLauncher` uses port 8000 by default. If you change the port, update `HYPATIA_PORT` in your `.env` or launch the backend separately with `run_dev.sh`.

---

## Database locked

**Symptom**: API requests fail with `database is locked` errors. The error response includes `code: "DB_LOCKED"`.

**Cause**: SQLite allows only one writer at a time. This typically happens when:
- Multiple instances of the app are running against the same data directory.
- A previous backend process didn't shut down cleanly.

**Solution**:

1. Make sure only one instance of Hypatia is running. Check for stale backend processes:
   ```bash
   # Windows
   tasklist | findstr uvicorn

   # macOS/Linux
   ps aux | grep uvicorn
   ```

2. Kill any stale processes, then restart the app.

3. If the issue persists, the database WAL file may be corrupted. Back up your data directory, then try:
   ```bash
   cd ~/.hypatia/data
   sqlite3 hypatia.db "PRAGMA wal_checkpoint(TRUNCATE);"
   ```

---

## Copilot CLI not installed (default provider)

**Symptom**: The default LLM provider (`copilot`) fails with errors about missing the GitHub Copilot CLI.

**Solution**: Either install the Copilot CLI or switch to a different provider.

**Switch provider** (recommended for most users):

1. Open **Settings** in the app, or set in `backend/.env`:
   ```bash
   HYPATIA_LLM_PROVIDER=anthropic   # or openai
   HYPATIA_ANTHROPIC_API_KEY=sk-ant-...
   ```

2. Restart the backend.

**Install Copilot CLI** (if you have a GitHub Copilot subscription):

Follow the [GitHub Copilot CLI docs](https://docs.github.com/en/copilot/using-github-copilot/using-github-copilot-in-the-command-line) to install and authenticate.

---

## Video transcription is slow

**Symptom**: Video/audio files take a very long time to process.

**Cause**: The default Whisper model (`base`) runs on CPU, which is slow for long recordings.

**Solution**:

- **Use a smaller model**: Set `HYPATIA_WHISPER_MODEL_SIZE=tiny` in `.env` for faster (less accurate) transcription.
- **Use GPU acceleration**: If you have an NVIDIA GPU with CUDA:
  ```bash
  HYPATIA_WHISPER_DEVICE=cuda
  ```
- For very long recordings (2+ hours), processing may take 10-30 minutes even with GPU. The task indicator in the sidebar shows progress.

---

## Backend won't start (missing dependencies)

**Symptom**: Import errors or module-not-found errors when starting the backend.

**Solution**: Re-run setup to reinstall dependencies:

```bash
cd backend
pip install -e ".[dev]"
```

Or run the full setup script:

```bash
scripts/setup.sh
```

If you see errors about `aiosqlite` or `sqlalchemy`, ensure you're using the virtual environment:

```bash
# Windows
backend\.venv\Scripts\activate

# macOS/Linux
source backend/.venv/bin/activate
```

---

## Wiki pages are empty after upload

**Symptom**: Files upload successfully but no wiki pages are generated.

**Cause**: Wiki generation requires a working LLM provider. If the provider is misconfigured, file conversion succeeds but wiki page creation fails silently.

**Solution**:

1. Check that your LLM provider is configured correctly (see "LLM API key invalid" above).
2. Check the backend logs at `~/.hypatia/logs/hypatia.log` for LLM-related errors.
3. Try running `/rebuild` in the chat panel to regenerate wiki pages from existing sources.

---

## "No flashcards could be generated" or an empty quiz

**Symptom**: Creating a deck or quiz fails with "No flashcards could be generated from the selected wiki pages" (or "No quiz questions ...").

**Cause**: Study material is built from wiki pages, not raw uploads. Offline generation needs concept or entity pages with a definition or opening paragraph, tables, or bold terms. Source summaries, the index, and the log produce few or no cards. A topic search with no matching pages, or a source file that no wiki page cites yet, also gives an empty scope. Offline multiple choice needs at least four cards from four different pages, and matching needs four cards with short answers.

**Solution**:

1. Wait until uploads finish ingesting and the wiki tree shows concept pages.
2. Widen the scope to **Whole class**, or use a broader topic.
3. Use **AI** or **Hybrid** if a model is configured; they write questions from any page content.
4. For quizzes, add more question types so others can make up for types the pages can't supply.

---

## AI and Hybrid are greyed out when creating study material

**Symptom**: The Create study material dialog only allows **Offline**, or `/flashcards` and `/quiz` reply that they were "built offline".

**Cause**: The app could not reach the configured LLM provider. Offline generation is always available.

**Solution**: Check the provider status in the sidebar and re-test the connection (see "LLM API key invalid" above). The dialog re-checks when the provider settings change; chat commands re-check at most every 30 seconds.

---

## AI study generation failed or disappeared

**Symptom**: A job in the Study tab shows an error, or "Lost track of this job; the backend may have restarted."

**Cause**: AI generation runs as a background task. It fails when every batch of pages fails at the LLM (rate limits, timeouts, context-size errors with small local models) or when no generated item cited a page. Tasks are kept in memory, so a backend restart forgets running jobs; nothing partial is saved.

**Solution**: Dismiss the job and try again, with a narrower scope or fewer cards for small local models. The backend log has the per-batch errors (`study_llm_batch_failed`).

---

## Short answers say "Check yourself" instead of a grade

**Symptom**: After submitting a quiz, short answers show **Check yourself** with the model answer.

**Cause**: The quiz was created with AI grading turned off, or the LLM could not be reached or returned no score while grading.

**Solution**: Compare your answer with the model answer and choose **I got it right** or **I got it wrong**; the score updates. To get AI grading on later quizzes, keep **Grade short answers with AI** on when creating them and check the provider connection.

---

## Cards or questions marked out of date

**Symptom**: A deck or quiz shows the out-of-date icon, or a card shows "The wiki page behind this card has changed."

**Cause**: The wiki page a card or question came from was edited, re-ingested, rebuilt, or removed after it was generated. Changes to page metadata alone do not count.

**Solution**: In a deck, use **Update from wiki** to re-extract offline cards (review history is kept when the question still exists). AI-written and your own cards stay flagged: choose **Keep**, **Edit**, or **Delete** on each. For quizzes, create a new quiz.

---

## Importing an exported deck into Anki

**Symptom**: Anki shows the header lines as cards, or cloze cards import as plain text.

**Solution**: Export with **Export for Anki** (not CSV) and import the `.anki.txt` file through **File > Import** in Anki 2.1.55 or later, which reads the file's header lines to pick the Basic and Cloze note types. The CSV export is meant for Quizlet and other tools that take plain front/back columns.

---

## Logs location

Backend logs are written to `~/.hypatia/logs/hypatia.log` (rotating, JSON-structured). Override with `HYPATIA_LOGS_DIR` in `.env`.

To watch logs in real time:

```bash
# Windows PowerShell
Get-Content -Wait ~/.hypatia/logs/hypatia.log

# macOS/Linux
tail -f ~/.hypatia/logs/hypatia.log
```
