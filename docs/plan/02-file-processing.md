# Phase 2: File Processing Pipeline

**Goal**: Build the backend services that convert uploaded files (documents, images, videos) into LLM-friendly markdown with metadata. This is the "raw source -> readable text" bridge that feeds the wiki engine.

**Prerequisites**: Phase 1 (database schema, FastAPI skeleton).

**Outputs**: Given any supported file, the pipeline produces a markdown conversion stored alongside the original, with metadata (page count, duration, timestamps).

---

## Tasks

### 2.1 Implement storage service
Create `app/services/storage_service.py`:
- `create_class_directories(class_id)` — creates the `data/classes/{class_id}/{raw,converted,wiki,thumbnails}` tree.
- `save_raw_file(class_id, filename, file_bytes)` — saves an uploaded file to `raw/`, returns the path.
- `get_raw_path(class_id, filename)` — resolves the full path to a raw file.
- `get_converted_path(class_id, filename)` — resolves where the markdown conversion should go.
- `delete_class_directory(class_id)` — removes the entire class data tree.
- `delete_file(class_id, filename)` — removes a file from raw/ and its conversion from converted/.
- Handle filename collisions (append counter or UUID suffix).

**Acceptance**: Can save, retrieve, and delete files. Directory structure is created correctly.

---

### 2.2 Integrate MarkItDown for document conversion
Create `app/services/file_converter.py`:
- Install `markitdown[all]` (or specific format extras: `pdf`, `docx`, `pptx`, `xlsx`).
- `convert_document(file_path: Path) -> ConversionResult` — calls MarkItDown to convert a file to markdown.
- `ConversionResult` contains: `markdown_text`, `metadata` (page count, word count, etc.), `success`, `error`.
- Write the markdown output to `converted/{original_name}.md`.
- Handle conversion errors gracefully (unsupported format, corrupted file).
- Supported formats: PDF, DOCX, PPTX, XLSX, CSV, HTML, images (with EXIF/OCR), plain text, markdown (passthrough).

**Acceptance**: Can convert a sample PDF, DOCX, and PPTX to markdown. Output is readable and preserves structure.

---

### 2.3 Implement video audio extraction with ffmpeg
Create the first stage of `app/services/video_processor.py`:
- `extract_audio(video_path: Path, output_path: Path) -> Path` — uses ffmpeg (via `subprocess`) to extract audio from a video file.
- Output format: WAV (16kHz mono) for optimal speech recognition compatibility.
- Extract video metadata: duration, resolution, codec, frame rate.
- Handle ffmpeg not being installed (clear error message).
- Handle audio-only files (mp3, m4a, wav) — skip video processing, go straight to transcription.

**ffmpeg command**:
```bash
ffmpeg -i input.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 output.wav
```

**Acceptance**: Can extract audio from an MP4 file. Metadata is captured correctly.

---

### 2.4 Implement speech-to-text transcription with timestamps
Extend `app/services/video_processor.py`:
- `transcribe_audio(audio_path: Path) -> TranscriptionResult` — uses **`faster-whisper`** (CTranslate2 backend) for transcription.
- Install `faster-whisper`.
- Produce timestamped segments: `[{start: float, end: float, text: str}, ...]`.
- `faster-whisper` natively returns word-level and segment-level timestamps.
- Support configurable Whisper model size (tiny, base, small, medium) for speed/accuracy tradeoff. Default: `base`.
- Support optional GPU acceleration (CUDA) via `faster-whisper`'s `device` parameter.

**Acceptance**: Can transcribe a sample video's audio and produce timestamped text segments.

---

### 2.5 Generate timestamped markdown from transcription
Extend `app/services/video_processor.py`:
- `generate_transcript_markdown(segments, video_filename) -> str` — converts timestamped segments into a structured markdown document.
- Format:
  ```markdown
  ---
  source: lecture-1.mp4
  type: transcript
  duration: "01:23:45"
  ---

  # Transcript: lecture-1.mp4

  ## [00:00:00 - 00:00:32](hypatia://open?file=lecture-1.mp4&t=0)
  Welcome to today's lecture on neural networks...

  ## [00:00:32 - 00:01:15](hypatia://open?file=lecture-1.mp4&t=32)
  Let's start by reviewing the basic architecture...
  ```
- Each segment header includes a deep-link URI that the frontend can parse to open the video at that timestamp.
- Write the output to `converted/{video_name}.md`.
- Also write `converted/{video_name}.metadata.json` with duration, segment count, model used.

**Acceptance**: A video file produces a markdown transcript with clickable timestamp headers.

---

### 2.6 Implement the full video processing pipeline
Create the orchestration function in `app/services/video_processor.py`:
- `process_video(class_id, file_path) -> ProcessingResult`:
  1. Extract audio from video (Task 2.3)
  2. Transcribe audio with timestamps (Task 2.4)
  3. Generate markdown transcript (Task 2.5)
  4. Clean up intermediate WAV file
  5. Update file record status in database
- Run as a background task (not blocking the upload endpoint).
- Report progress via database status field: `pending` -> `processing` -> `ready` or `error`.

**Acceptance**: End-to-end: upload a video -> background processing -> markdown transcript appears in converted/.

---

### 2.7 Create file type detection and routing
Create a dispatcher in `app/services/file_converter.py`:
- `process_file(class_id, file_path) -> ProcessingResult` — detects file type and routes to the correct processor:
  - Video/audio files (mp4, avi, mov, mkv, mp3, wav, m4a) -> `video_processor.process_video()`
  - Documents (pdf, docx, pptx, xlsx, csv, html) -> `file_converter.convert_document()` (MarkItDown)
  - Images (png, jpg, gif, webp) -> `file_converter.convert_document()` (MarkItDown with OCR/EXIF)
  - Markdown/text (md, txt) -> passthrough (copy to converted/ with frontmatter)
- Use file extension and/or MIME type for detection.
- Unknown types -> attempt MarkItDown, fall back to error.

**Acceptance**: Different file types are routed correctly to their respective processors.

---

### 2.8 Generate source summaries (markdown)
After conversion, create a brief summary of each file:
- For documents: first N paragraphs + key headings + metadata block.
- For video transcripts: overall topic + key timestamps + duration.
- Store as `converted/{filename}.summary.md`.
- This summary is what the wiki engine will use for the source-summary wiki page.

**Acceptance**: Each processed file has both a full conversion and a summary.

---

### 2.9 Implement background task queue
- Use FastAPI's `BackgroundTasks` or a simple async task queue for file processing.
- File upload returns immediately with `status: "processing"`.
- Enforce a **3GB file size limit** on upload. Return 413 if exceeded.
- Frontend can poll `GET /api/files/{file_id}` to check status.
- Consider `asyncio.Queue` for ordering if multiple files are uploaded simultaneously.
- Store task progress in the database (status field on file record).

**Acceptance**: File upload returns instantly. Processing happens in background. Status is queryable.

---

### 2.10 Write tests for file processing
- Test MarkItDown conversion with sample files (PDF, DOCX, PPTX).
- Test video audio extraction (requires ffmpeg + a short test video).
- Test transcription with faster-whisper (can mock for unit tests, integration test with real audio).
- Test file type routing.
- Test error handling (corrupted files, unsupported formats, missing ffmpeg).

**Acceptance**: Test suite passes. Edge cases (bad files, large files) are covered.

---

## Sequencing

```
2.1 (storage) ──→ 2.2 (MarkItDown) ──→ 2.7 (routing) ──→ 2.8 (summaries)
                                                       └──→ 2.9 (bg tasks)
             ──→ 2.3 (ffmpeg) ──→ 2.4 (whisper) ──→ 2.5 (transcript md) ──→ 2.6 (pipeline)
                                                                          └──→ 2.7 (routing)
2.10 (tests) — after all above
```

- 2.1 first (storage is needed by everything).
- 2.2 (MarkItDown) and 2.3 (ffmpeg) can run in parallel.
- 2.4 depends on 2.3; 2.5 depends on 2.4; 2.6 depends on 2.3+2.4+2.5.
- 2.7 depends on 2.2 and 2.6.
- 2.8 and 2.9 depend on 2.7.
- 2.10 is last.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Whisper model download is large (base=~150MB, small=~500MB) | Default to `base` model. Document model sizes. Allow user to configure. `faster-whisper` models are smaller than `openai-whisper` equivalents. |
| ffmpeg not installed on user's system | Check on startup, provide clear error message with install instructions. |
| Very long videos (>2 hours) produce huge transcripts | Chunk transcript into logical segments. Consider time-based splitting. |
| MarkItDown fails on some PDFs (scanned images) | Fall back to OCR-based extraction. Document limitations. |
