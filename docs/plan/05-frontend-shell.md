# Phase 5: Frontend Shell

**Goal**: Build the Flutter app's structural skeleton — the 3-panel layout, navigation, Class switching, and the basic widget hierarchy. No backend integration yet; this phase uses mock data.

**Prerequisites**: Phase 1 (Flutter project initialized).

**Outputs**: A navigable Flutter app with the correct layout, class dropdown, sidebar, wiki viewer panel, and chat panel — all rendering static/mock content.

**Status**: COMPLETE

---

## Implementation Notes (deviations from original plan)

1. **BackendGate preserved**: The existing `BackendGate` widget from Phase 1 (Task 1.9) remains the app's startup gate. The `HypatiaShell` (with `MaterialApp.router` + GoRouter) only renders after `BackendStatus.ready`. This avoids duplicating the backend lifecycle management.
2. **`shared_preferences` added**: Required for theme persistence (not in the original Phase 1 deps).
3. **`ProviderScope` wrapping**: Added at the `runApp` level in `main()` for Riverpod to work.
4. **Enum naming**: `WikiCategory.index` conflicted with Dart's built-in `Enum.index` getter — renamed to `WikiCategory.wikiIndex` and `WikiCategory.wikiLog`.
5. **Class creation dialog**: Integrated directly into `class_dropdown.dart` rather than a separate file, since it's only accessible from the dropdown.
6. **`DropdownButtonFormField.value`**: Deprecated in Flutter 3.33+ — use `initialValue` instead.
7. **`Color.withOpacity`**: Deprecated — replaced with `Color.withValues(alpha: ...)` throughout.

---

## UI Reference

The layout is modeled after the MindBase UI (see `docs/ui.png`) with these modifications:
- **Top bar**: Shows "Hypatia" (not "MindBase"). Contains a class dropdown selector.
- **Left sidebar**: Class dropdown at top, search bar, wiki file tree (expandable categories), and an "Add Files" button.
- **Center panel**: Wiki page viewer (renders markdown).
- **Right panel**: Chat interface with command input.

```
┌──────────────────────────────────────────────────────┐
│  Hypatia        [Class Dropdown ▼]                   │
├──────────┬─────────────────────────┬─────────────────┤
│ Sidebar  │     Wiki Viewer         │  Chat Panel     │
│          │                         │                 │
│ [Search] │  # Page Title           │  [Starter cards]│
│          │                         │                 │
│ ▼ Wiki   │  Content with           │  ...            │
│   page1  │  [[links]] and          │                 │
│   page2  │  citations [src]        │  ...            │
│ ▼ Sources│                         │                 │
│   file1  │                         │  [Ask anything] │
│   file2  │                         │  /command...    │
│          │                         │                 │
│ [+ Add]  │                         │                 │
└──────────┴─────────────────────────┴─────────────────┘
```

---

## Tasks

### 5.1 Set up app shell and routing
In `lib/app.dart`:
- Configure `MaterialApp` with `GoRouter`.
- Define routes:
  - `/` — home screen (redirects to last-used class or class creation)
  - `/class/:classId` — main 3-panel view for a Class
- Set up theme (dark mode support from the start, matching the MindBase aesthetic).
- Configure window sizing for desktop (minimum size, default size).

**Acceptance**: App launches. Navigation between routes works. Theme is applied.

---

### 5.2 Implement 3-panel layout
In `lib/screens/home_screen.dart`:
- Build a responsive 3-panel layout:
  - Left sidebar: fixed width (~250px), collapsible.
  - Center wiki viewer: flexible, fills available space.
  - Right chat panel: fixed width (~350px), collapsible.
- Use `Row` with `Expanded` and constrained `SizedBox` children.
- Add draggable dividers between panels for resizing.
- On smaller screens (mobile/tablet), stack panels vertically or use tabs.

**Acceptance**: Three panels render side-by-side on desktop. Panels are resizable. Layout doesn't overflow.

---

### 5.3 Build sidebar widget
Create `lib/widgets/sidebar/sidebar.dart` and sub-widgets:
- **Class dropdown** (`class_dropdown.dart`):
  - Shows current class name.
  - Dropdown lists all classes.
  - "New Class" option at the bottom opens a creation dialog.
  - Indicates the currently selected class.
- **Search bar** (`search_bar.dart`):
  - Text input with search icon.
  - Placeholder: "Search wiki..."
  - Triggers search on Enter (connected in Phase 6).
- **Wiki tree** (`wiki_tree.dart`):
  - Expandable tree view matching the wiki directory structure.
  - Categories: Wiki (index, pages), Sources (raw files), Logs.
  - Each item shows name and count.
  - Clicking a wiki page loads it in the center panel.
  - Clicking a source file opens it (via deep link).
- **Add Files button** (`add_file_button.dart`):
  - Prominent button at the bottom of the sidebar.
  - Opens a file picker dialog (connected in Phase 6).

**Acceptance**: Sidebar renders with all components. Tree is expandable/collapsible. Class dropdown shows mock classes.

---

### 5.4 Build wiki viewer widget
Create `lib/widgets/wiki_viewer/wiki_viewer.dart`:
- Renders markdown content in the center panel.
- Uses `flutter_markdown` or `markdown_widget` package.
- Header shows: page title, "Last built" date, "Rebuild" button.
- Navigation: back/forward buttons for page history.
- Placeholder state when no page is selected: "Select a wiki page from the sidebar."

**Acceptance**: Can render a mock markdown page with headings, lists, links, and code blocks.

---

### 5.5 Build chat panel widget
Create `lib/widgets/chat_panel/chat_panel.dart` and sub-widgets:
- **Header**: "New Conversation" with a "+" button to start fresh.
- **Starter cards** (`starter_cards.dart`):
  - Shown when chat is empty.
  - Cards: "Ask about my wiki", "Summarize a topic", "Add files".
  - Each card has an icon, title, and subtitle.
- **Message list**: scrollable list of message bubbles.
  - **Message bubble** (`message_bubble.dart`): user messages right-aligned, assistant messages left-aligned. Assistant messages render markdown.
- **Command input** (`command_input.dart`):
  - Text field at the bottom.
  - Placeholder: "Ask anything, drop a link, /command..."
  - Send button.
  - Supports `/ask`, `/summarize`, `/remove`, `/lint`, `/rebuild`, `/export` commands.
  - Shows command autocomplete when typing `/`.

**Acceptance**: Chat panel renders with starter cards. Can type and display mock messages. Command input recognizes `/` prefix.

---

### 5.6 Set up Riverpod state management
Create providers in `lib/providers/`:
- `class_provider.dart`:
  - `classListProvider` — list of all Classes.
  - `currentClassProvider` — currently selected Class.
  - `currentClassIdProvider` — just the ID (used for routing).
- `wiki_provider.dart`:
  - `wikiTreeProvider(classId)` — wiki page tree for sidebar.
  - `currentWikiPageProvider` — currently viewed page content.
- `chat_provider.dart`:
  - `chatMessagesProvider(classId)` — list of chat messages.
  - `chatInputProvider` — current input text.
- `file_provider.dart`:
  - `fileListProvider(classId)` — list of files in current class.

Initially, all providers return mock data. They'll be connected to the API in Phase 6.

**Acceptance**: Providers are defined. Widgets rebuild when provider state changes. Mock data flows correctly through the UI.

---

### 5.7 Implement Class creation dialog
Create a dialog/modal for creating a new Class:
- Fields: Name (required), Description (optional).
- Validation: Name must not be empty, must be unique.
- On submit: adds to class list, switches to the new class.
- Accessible from: class dropdown "New Class" option, and empty state.

**Acceptance**: Dialog opens, validates input, creates a mock class, and switches to it.

---

### 5.8 Implement dark/light theme
In `lib/config/theme.dart`:
- Define dark and light theme data.
- Match the MindBase aesthetic: dark sidebar, clean content area, subtle borders.
- Theme toggle in sidebar or settings.
- Persist theme preference (shared_preferences).

**Acceptance**: App supports both themes. Toggle works. Theme persists across restarts.

---

## Sequencing

```
5.1 (shell/routing) ──→ 5.2 (3-panel) ──→ 5.3 (sidebar)
                                       ──→ 5.4 (wiki viewer)
                                       ──→ 5.5 (chat panel)
5.6 (providers) — build alongside 5.3-5.5
5.7 (class dialog) — after 5.3 (class dropdown)
5.8 (theme) — can be done anytime, ideally early
```

- 5.1 first, then 5.2.
- 5.3, 5.4, 5.5 can be built in parallel after 5.2.
- 5.6 develops alongside the widgets.
- 5.7 after 5.3.
- 5.8 anytime.
