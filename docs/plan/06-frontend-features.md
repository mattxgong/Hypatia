# Phase 6: Frontend Features

**Goal**: Connect the Flutter frontend to the FastAPI backend. Replace mock data with real API calls. Implement file upload, wiki page rendering with clickable citations, user-editable wiki pages, chat with streaming, and all 6 command interactions.

**Prerequisites**: Phase 4 (backend API is complete), Phase 5 (frontend shell with mock data).

**Outputs**: A fully functional application where users can create Classes, upload files, browse and edit the generated wiki, and chat with their knowledge base using /ask, /summarize, /remove, /lint, /rebuild, and /export.

---

## Tasks

### 6.1 Implement API client service
Create `lib/services/api_client.dart`:
- HTTP client (using `dio` or `http` package) configured with base URL.
- Methods for every backend endpoint:
  - `getClasses()`, `createClass()`, `deleteClass()`
  - `getFiles(classId)`, `uploadFile(classId, file)`, `deleteFile(classId, fileId)`
  - `getWikiTree(classId)`, `getWikiPage(classId, pagePath)`, `updateWikiPage(classId, pagePath, content)`, `rebuildWiki(classId)`, `lintWiki(classId)`, `exportWiki(classId)`
  - `getChatHistory(classId)`, `clearChatHistory(classId)`
  - `searchWiki(classId, query)`
- Error handling: network errors, server errors, timeouts.
- Base URL configuration (localhost:8000 in dev, configurable for production).

**Acceptance**: All API methods work against the running backend. Error cases are handled.

---

### 6.2 Implement WebSocket service for chat
Create `lib/services/websocket_service.dart`:
- Manages a WebSocket connection to `/api/classes/{class_id}/chat`.
- `connect(classId)` — establishes connection.
- `sendMessage(content)` — sends a chat message (command or plain text).
- `onChunk` — stream of response chunks (for token-by-token rendering).
- `onComplete` — notification when response is finished (includes citations).
- `disconnect()` — closes connection.
- Auto-reconnect on connection loss.
- Connection status tracking (connected, disconnecting, reconnecting).

**Acceptance**: WebSocket connects to backend. Messages send and responses stream back in real-time.

---

### 6.3 Connect providers to API
Update all providers in `lib/providers/` to use real API calls instead of mock data:
- `classListProvider` — calls `apiClient.getClasses()`.
- `currentClassProvider` — loaded when class is selected.
- `wikiTreeProvider` — calls `apiClient.getWikiTree(classId)`.
- `currentWikiPageProvider` — calls `apiClient.getWikiPage(classId, path)`.
- `chatMessagesProvider` — loads from `apiClient.getChatHistory(classId)`, updated by WebSocket.
- `fileListProvider` — calls `apiClient.getFiles(classId)`, polls for processing status.
- Handle loading states (show spinners), error states (show error messages), and empty states.

**Acceptance**: All UI components display real data from the backend. Loading and error states render correctly.

---

### 6.4 Implement file upload flow
Connect `add_file_button.dart` to real file upload:
- Open file picker (using `file_picker` package).
- Support multiple file selection.
- Show upload progress (upload percentage, then processing status).
- Supported file types: PDF, DOCX, PPTX, XLSX, CSV, TXT, MD, MP4, AVI, MOV, MKV, MP3, WAV, M4A, PNG, JPG, GIF.
- After upload, show the file in the sidebar with its processing status.
- When processing completes, refresh the wiki tree (new pages may have been generated).
- Handle drag-and-drop onto the app window (desktop).

**Acceptance**: Can select and upload files. Progress is shown. Wiki tree updates when processing completes.

---

### 6.5 Implement markdown rendering with citation links
Update `lib/widgets/wiki_viewer/markdown_renderer.dart`:
- Render markdown using `flutter_markdown` with custom builders.
- Handle wiki links `[[page-name]]` — render as clickable links that navigate to the referenced wiki page.
- Handle citation links `[text](hypatia://cite?file=...&loc=...)`:
  - Render as a small superscript or inline link icon.
  - On click: open the referenced source file at the specified location.
  - For PDFs: open in a PDF viewer at the specified page.
  - For videos: open in a video player seeked to the timestamp.
  - For text: open and scroll to the specified line/section.
- Handle standard markdown links (external URLs open in browser).
- Render frontmatter as a metadata header (title, tags, source count).

**Acceptance**: Wiki pages render with clickable wiki links and citation links. Clicking a citation opens the source at the correct location.

---

### 6.6 Implement source file viewer
Create a viewer for opening source files when citation links are clicked:
- **PDF viewer**: Use `pdfx` or `syncfusion_flutter_pdfviewer` to render PDFs. Support jumping to a specific page.
- **Video player**: Use `media_kit` or `video_player` to play videos. Support seeking to a timestamp.
- **Text/Markdown viewer**: Render text with line highlighting for the cited location.
- **Image viewer**: Display images with zoom.
- Open in a new tab/panel or overlay dialog.
- "Back to wiki" button to return to the previous view.

**Acceptance**: All source file types can be opened from citation links. Location-based navigation works (PDF pages, video timestamps).

---

### 6.7 Implement chat with streaming responses
Connect `chat_panel.dart` to the WebSocket service:
- Send messages through the WebSocket.
- Render streaming responses token-by-token (append to the assistant message as chunks arrive).
- Parse commands from input: recognize `/ask`, `/summarize`, `/remove`, `/lint`, `/rebuild`, `/export` and display appropriate UI feedback.
- Show typing indicator while the LLM is generating.
- After `/summarize` completes: refresh the wiki tree (new page was added).
- After `/remove` completes: refresh both file list and wiki tree.
- After `/lint` completes: display the lint report in the chat (structured list of issues).
- After `/rebuild` completes: refresh the entire wiki tree. Show progress during rebuild.
- After `/export` completes: trigger a file download of the exported wiki.
- Display citations in assistant responses as clickable links.
- Scroll to bottom on new messages.

**Acceptance**: Chat messages send and stream back. Commands trigger appropriate actions. Wiki/file lists update after commands.

---

### 6.8 Implement file processing status tracking
Show real-time processing status for uploaded files:
- In the sidebar file list: show status indicator (spinner for processing, checkmark for ready, X for error).
- Poll `GET /api/classes/{class_id}/files/{file_id}` every few seconds while status is "processing".
- When status changes to "ready": refresh wiki tree, show a notification.
- When status changes to "error": show the error message.
- For video files: show estimated processing time (based on duration).

**Acceptance**: File processing status is visible in the UI. Status transitions trigger appropriate updates.

---

### 6.9 Implement search functionality (basic)
Connect the sidebar search bar to the backend:
- Call `GET /api/classes/{class_id}/wiki/search?q=...` on Enter.
- Display results in the sidebar (replacing the wiki tree temporarily).
- Each result shows: page title, category, snippet with highlighted match.
- Clicking a result navigates to that wiki page.
- Clear search to return to the wiki tree view.
- Debounce search input (300ms) for live search.

**Acceptance**: Search returns relevant wiki pages. Results are clickable. Can clear search to return to tree view.

---

### 6.10 Implement wiki page editing
Enable users to edit wiki pages directly in the wiki viewer:
- Add an "Edit" button to the wiki page header (next to the title).
- Toggle between view mode (rendered markdown) and edit mode (raw markdown editor).
- In edit mode: show a text area with the raw markdown content, "Save" and "Cancel" buttons.
- On save: call `apiClient.updateWikiPage(classId, pagePath, content)`.
- The backend marks the page as user-edited (tracked separately from LLM content).
- Show a visual indicator on user-edited pages (e.g., a small "edited" badge in the sidebar tree).
- User edits survive `/rebuild` — the LLM merges around them.

**Acceptance**: Can edit a wiki page inline. Edits persist. User-edited pages are visually distinguished. Edits survive rebuilds.

---

### 6.11 Implement Class management
Connect class-related UI to the API:
- Class creation dialog calls `apiClient.createClass()`.
- Class dropdown loads from `apiClient.getClasses()`.
- Switching classes: updates the current class, loads new wiki tree, loads new file list, disconnects/reconnects chat WebSocket.
- Class deletion: confirmation dialog, calls `apiClient.deleteClass()`, switches to another class or empty state.
- Show class stats in the dropdown or a details view (file count, page count, last updated).

**Acceptance**: Can create, switch between, and delete Classes. All data updates when switching.

---

### 6.12 Implement empty states and onboarding
Design empty states for each panel:
- **No Classes exist**: "Welcome to Hypatia. Create your first Class to get started." with a create button.
- **Class has no files**: "Upload files to build your knowledge base." with an upload button.
- **Wiki is empty**: "No wiki pages yet. Upload source material and the wiki will be generated automatically."
- **Chat is empty**: Show starter cards (from Phase 5.5), connected to real actions.

**Acceptance**: All empty states render with clear calls to action. First-time user experience is smooth.

---

### 6.13 Add error handling and notifications
- Show toast notifications for: upload complete, processing complete, wiki rebuilt, errors.
- Show error dialogs for: network errors, server errors, LLM errors.
- Retry logic for transient network errors.
- Graceful degradation when backend is unreachable.

**Acceptance**: Users see feedback for all operations. Errors are communicated clearly.

---

## Sequencing

```
6.1 (API client) ──→ 6.3 (connect providers)
6.2 (WebSocket) ──→ 6.7 (streaming chat)
6.3 (providers) ──→ 6.4 (file upload)
               ──→ 6.5 (markdown + citations) ──→ 6.6 (source viewer)
                                               ──→ 6.10 (wiki editing)
               ──→ 6.8 (processing status)
               ──→ 6.9 (search)
               ──→ 6.11 (class management)
6.12 (empty states) — after 6.3
6.13 (error handling) — throughout, finalized last
```

- 6.1 and 6.2 first (they're the transport layer).
- 6.3 second (connects UI to data).
- 6.4-6.11 can be built in parallel after 6.3, though 6.6 and 6.10 depend on 6.5, and 6.7 depends on 6.2.
- 6.12 and 6.13 are polish, done throughout and finalized last.

---

## Implementation Notes (Post-Completion)

**Status**: Phase 6 complete. All tasks implemented and passing `flutter analyze` + `dart format`.

### Key decisions and deviations from original plan

1. **Dio chosen over `http`** for the API client — multipart upload, interceptors, and structured error parsing are much easier with Dio.

2. **Model alignment was substantial**: Frontend models diverged significantly from the API contract during Phase 5 (mock data). All models were rewritten with `fromJson`/`toJson` and field additions (`fileSizeBytes`, `rawPath`, `convertedPath`, `errorMessage`, `metadataJson`, `updatedAt` on SourceFile; `id`/`classId`/`sourceFileIds` on WikiPage; `synthesis` WikiCategory).

3. **file_picker v12 breaking changes**: The `FilePicker.platform.pickFiles()` API from earlier versions was replaced with static `FilePicker.pickFiles()`. The `allowMultiple` parameter is deprecated (multi-select is now the default for `pickFiles`).

4. **Source viewer is scaffolding only**: Full video playback (`media_kit`) and PDF rendering (`pdfrx`/`syncfusion`) require heavy native dependencies and platform-specific setup. The current implementation fetches converted text content and displays it in a monospace dialog. Full media support is deferred to Phase 8.

5. **Drag-and-drop (`desktop_drop`) deferred**: Not added in this phase to avoid additional native dependencies. Can be added incrementally later.

6. **Provider architecture**: All providers migrated from sync `Notifier`/`StateProvider` to `AsyncNotifierProvider`, `FutureProvider.family`, or `NotifierProvider.family` to properly handle loading/error states with `AsyncValue.when()`.

7. **WebSocket auto-reconnect**: Implemented with exponential backoff (1s → 2s → 4s → ... → 32s cap). Connection state exposed as an enum stream.

8. **`backendBaseUrlProvider`**: Introduced as a `StateProvider<String>` set by `BackendGate` when the backend becomes ready, rather than hardcoding port 8000.

### Deferred to later phases

- Full media playback in source viewer (media_kit + pdfrx native deps) → **Phase 7 (task 7.8)**
- Drag-and-drop file upload (desktop_drop) → **Phase 7 (task 7.7)**
- Upload progress percentage (Dio progress callback wired to UI) → **Phase 7 (task 7.6)**
- `backup` and `tasks` API integration → Phase 8
- Class stats display in dropdown → Phase 8
