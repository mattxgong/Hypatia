# Phase 10 (proposed): Mobile App (iOS / Android)

**Goal**: Let a user use Hypatia from a phone or tablet: read the wiki, chat with a Class,
review flashcards and take quizzes (including offline), and capture new source material
(photos, recordings, shared files) into a Class.

**Prerequisites**: Phases 1-9 complete, plus wave A of [Phase 11](./11-study-and-ux.md)
(11.1-11.5: quiz data changes, theme tokens and pane rules). The desktop app is the reference
client.

**Outputs**: An authenticated remote-access mode for the backend, Android and iOS targets
in `frontend/`, a responsive compact layout, an offline study cache with a review queue,
local due-card notifications, and mobile build and release jobs in CI.

**Status**: Planning only, not started. Revised 2026-10-20 (implementation order added). Decisions below; the remaining
open questions are in §10. The implementation order is in §9.

**Decisions (2026-10-18)**:
- **Backend**: companion to the desktop now (Option A), designed so a hosted backend
  (Option B) can be added later without reworking the client (see "Keeping hosted mode
  possible" in §2).
- **Platforms**: Android first. iOS-specific tasks (§6.2, iOS signing, Share Extension)
  are deferred, but shared code must not block iOS (no Android-only APIs outside platform guards).
- **Distribution**: personal use only. Signed APK via GitHub Releases or `adb install`.
  Store listings, demo mode, privacy-policy and data-safety work (§6.4) are out of scope.
- **v1 scope**: read wiki + chat, offline study, capture (camera, audio, share sheet),
  and due-card notifications.

**Decisions (2026-10-19)**:
- **Remote reach**: LAN **and** Tailscale (10.3). No direct internet exposure.
- **Device permissions**: a paired device has **full permissions**, the same as the
  desktop client (10.2).
- **Desktop lifetime**: the backend keeps running in the **system tray** when the window
  closes (10.1).
- **Image OCR**: a **local OCR engine** in the ingestion pipeline (new task 10.13a). No
  vision-LLM step for now.
- **Tablets**: **first-class**, with tuned medium and expanded layouts (10.12).
- **Doc location**: moved from `docs/make-mobil-app.md` to `docs/plan/10-mobile.md`,
  linked from `00-master-plan.md` and `open-questions.md` (questions 4, 6, 11).
- **iOS tooling**: researched xtool for Mac-free iOS builds. Findings and the recommended
  pipeline for when iOS starts are in §6.5.

**Decisions (2026-10-19, second round)**:
- **Close-to-tray**: only while remote access is on. With remote access off, closing quits
  as it does today (10.1).
- **App lock**: none. The phone app doesn't ask for a biometric or screen-lock check; it
  relies on the phone's own lock screen (10.2).
- **Repo visibility**: public. GitHub-hosted macOS runner minutes are free, so the CI-built
  iOS pipeline (§6.5, pipeline A) costs nothing. Signing secrets need care in a public
  repo (§7).
- **iOS Apple account**: free Apple ID. That means 7-day reinstalls, at most 3 sideloaded
  apps per device, and no iOS Share Extension until xtool supports App Groups on free
  teams (§6.5).
- **App identifier**: `com.mattxgong.hypatia`, at least initially, for both the Android
  `applicationId` and the iOS bundle ID (10.9).

---

## 1. Review of the previous draft

The earlier version of this document described a codebase that doesn't match the repo.
Most of its gap analysis and code samples were wrong, so this revision replaces them.
The main corrections:

| Previous claim | Actual state (verified in code) |
|---|---|
| Chat uses "basic SSE" and needs a WebSocket upgrade | Chat is already a WebSocket: `backend/app/routers/chat.py` at `/api/classes/{class_id}/chat`, with streamed `chunk` / `complete` / `error` / task-progress frames. `frontend/lib/services/websocket_service.dart` already consumes it. |
| Auth uses `X-API-Key` and needs refresh tokens | There is **no auth at all**. The backend binds `127.0.0.1` (`backend_launcher.dart`) and trusts every caller. That's safe only because it's loopback-only. |
| Task polling every 60s | `task_provider.dart` and `file_provider.dart` poll every 3s, and `study_provider.dart` polls every 2s. Polling over LAN is fine, so a task WebSocket is optional. |
| "The backend API is designed for web use / deploy to a production server" | The backend is a local, single-user process. The desktop app spawns it as a subprocess (`backend_launcher.dart`, Open Question 5) and kills it on exit. The master plan says "single user, local deployment" and "mobile layout is a future phase". |
| "Backend doesn't need major changes" | That depends entirely on where the backend runs (§2). For a hosted backend it is the largest piece of work. |
| Platform UI "already mobile-first" | It isn't. `home_screen.dart` is a fixed 3-panel `Row` with drag-resize dividers, `DropTarget` (desktop_drop), and `window_manager`. There are no `android/` or `ios/` folders. |
| Use Gunicorn `-k gthread` | `gthread` is a WSGI worker and can't serve this ASGI app. More than one worker would also break the in-memory `task_manager` and the ingestion queue. Keep a single uvicorn process. |
| FCM push from the client using a server key | A client can't send FCM messages, and shipping a server key in the app would expose it. The legacy FCM server-key API was shut down in 2024. FCM also needs an always-on server, which the desktop model doesn't have. Local notifications cover the real use case (§5.7). |
| sqflite schema plus a trigger-driven sync | The schema had type and constraint errors, and SQLite triggers can't make network calls. SM-2 state is computed server-side (`services/study/scheduler.py`), so offline review needs a review-event queue, not a second copy of the schema (§5.6). |
| iOS "notarization required for App Store" | Notarization only applies to macOS apps distributed outside the App Store. |
| `Info.plist` with `NSAllowsArbitraryLoads`, `background-fetch`, `NSAppGroupContainers`, `UIAppFonts: System`, ... | Several of those keys or values don't exist. `NSAllowsArbitraryLoads` draws App Review scrutiny. The keys that are actually needed are listed in §6.2. |
| Android `WRITE_EXTERNAL_STORAGE`, `REQUEST_IGNORE_BATTERY_OPTIMIZATION`, a `dataSync` foreground service | None of these are needed. The file picker uses the Storage Access Framework, and battery-optimization exemptions and foreground services trigger Play policy declarations. `POST_NOTIFICATIONS` (Android 13+) and the cleartext or network-security config were missing. |
| "Deep linking: configure in Firebase Console" | Firebase Dynamic Links was shut down in 2025. Use App Links / Universal Links if deep links are needed at all. |
| Apple fee "$99/year (paid once)", review "2-4 weeks", 15% commission | It's $99 per year, renewing. Review usually takes 1-3 days. The commission is 30%, or 15% for the Small Business Program or for subscriptions after the first year, and the rules vary by region. |
| Phase 3: rewrite in Swift/Kotlin, or "consider React Native" | Dropped. Flutter is already cross-platform. A native rewrite would triple the maintenance burden for no clear gain, and nothing here needs native UI beyond plugins. |
| "Native UI improvements" (RecyclerView, UIActivityViewController, ...) | Flutter renders its own widgets and doesn't use those. The real mobile UI work is the responsive layout (§5.4). |
| Effort: "functional mobile app in 2-3 weeks" | Unrealistic for auth, a new layout, offline study, and store compliance. See §8. |
| References | Several links were broken or pointed to packages that don't exist (`kitural`, `flutter_platform_channel`, `jamierobert/sqflite`, `websocket`). |

---

## 2. The core decision: where does the backend run?

Everything else depends on this. The backend relies on desktop-class pieces: Python 3.11,
the `git` binary (`wiki_git.py`), `ffmpeg`/`ffprobe` and `faster-whisper`
(`video_processor.py`), MarkItDown's PDF/Office stack, the Copilot CLI (`copilot_provider.py`),
and optionally a local Ollama. It also stores up to 3 GB per upload (`max_upload_size_bytes`).

| Option | What it means | Pros | Cons |
|---|---|---|---|
| **A. Companion to desktop (recommended)** | The phone is a client of the user's own desktop backend over LAN, or remotely via a VPN such as Tailscale. | Keeps the local-first, single-user design and the privacy story. No server costs. API keys stay on the desktop. All providers, including Copilot and Ollama, keep working. Most of the backend is reused as-is. | The desktop must be on, awake, running Hypatia, and reachable. It needs pairing, auth, and TLS. No push notifications for ingestion events. Store reviewers can't test it without a desktop (§6.4). |
| B. Hosted cloud backend | A multi-user server you operate. | Works anywhere, needs no desktop, supports real push. | It's a different product. Every table and file path needs a `user_id`. You'd need accounts, password reset, and account deletion (Apple 5.1.1(v)), Postgres plus object storage, per-user git repos on the server, and GPU or API costs for Whisper. You'd hold users' LLM keys or pay for their usage. The Copilot provider can't serve other users from your subscription. You'd also take on privacy obligations for student material. Several months of work plus ongoing hosting cost. |
| C. Backend embedded on the device | Python runs inside the app (for example `serious_python`, or Chaquopy on Android). | Fully offline. | iOS forbids spawning subprocesses, so there's no `git` or `ffmpeg` (`ffmpeg-kit` was retired in 2025). `faster-whisper`/`ctranslate2` don't publish iOS wheels. App size would be hundreds of MB. Battery and thermal cost of on-device ingestion. Not viable without rewriting large parts of the backend. |
| D. Port the backend to Dart | Rewrite. | Native everywhere. | Rewrites phases 2-9. Not justified. |

**Recommendation: Option A.** It matches the master plan's assumptions, reuses the
existing API almost unchanged, and is the only option a solo developer can ship in weeks.
The phone covers what fits a phone: reading, chat, study, and capture. Heavy ingestion
stays on the desktop.

**Keeping hosted mode possible** (decided 2026-10-18). Constraints for A, so B is additive later:
- The client only ever knows a `baseUrl` plus a Bearer token. Never assume loopback or LAN
  in client logic. A hosted server would just issue different tokens.
- Put auth behind one FastAPI dependency (for example `get_principal()`) that returns a
  principal object (`device_id`). For now it identifies a device. Later it could
  carry a `user_id` that routers filter on.
- Keep all file access going through `storage_service.py` (it already does), so it can be
  swapped for object storage.
- Don't build features that depend on the backend reaching the desktop filesystem or OS
  (for example, `/files/{id}/open` on mobile should download, not open a desktop app).
- Not done now: multi-tenancy columns, Postgres, accounts, server push. Those belong to a
  future Phase 11 with its own plan.

A cheaper interim step is a **PWA served by the desktop backend** (Flutter web build).
It needs no app store, but it inherits all of Option A's networking and auth work, and
it adds some of its own. `dart:io` and `media_kit` need web alternatives. iOS PWAs have
limited background and notification support. Without TLS the page isn't a secure context.
It's worth considering only if store distribution is unwanted (§10).

---

## 3. Target architecture (Option A)

```
┌──────────── Desktop (always the source of truth) ─────────────┐
│ Flutter desktop app ── spawns ──> FastAPI backend (uvicorn)    │
│   (local token)                    ├─ SQLite, wiki git, files  │
│                                    ├─ LLM providers, whisper   │
│                                    └─ binds 127.0.0.1 by       │
│                                       default; 0.0.0.0 or a    │
│                                       Tailscale IP when remote │
│                                       access is enabled        │
└───────────────────────────────▲───────────────────────────────┘
                                │ HTTPS + WSS, Bearer device token
                                │ (LAN, pinned self-signed cert,
                                │  or Tailscale)
┌───────────────────────────────┴───────────────────────────────┐
│ Flutter mobile app (same codebase, compact layout)             │
│  ├─ Connection: QR pairing, URL + token in secure storage      │
│  ├─ Offline cache: decks, due cards, viewed wiki pages         │
│  ├─ Review queue: rating events replayed on reconnect          │
│  └─ Local notifications: "N cards due" from cached due_at      │
└────────────────────────────────────────────────────────────────┘
```

---

## 4. Backend tasks (10A)

### 10.1 Remote-access mode and process lifetime

- Add `remote_access_enabled: bool = False`, `bind_host`, and `remote_port` to
  `app/config.py`. Persist them via `settings_store.py`.
- `backend_launcher.dart` passes `--host 0.0.0.0` (or a chosen interface) only when remote
  access is enabled. Otherwise it keeps `127.0.0.1`. Changing the setting needs a backend restart.
- **Lifetime: system tray (decided 2026-10-19)**. Today the backend dies when the desktop
  app closes. Change that:
  - Add `tray_manager` (same author as the `window_manager` already in use). In `main.dart`,
    call `windowManager.setPreventClose(true)`, and have `onWindowClose` hide the window
    instead of exiting. The backend subprocess keeps running.
  - Decided behavior: closing to the tray only applies while remote access is enabled.
    With remote access off, closing quits exactly as today. Turning remote access off
    while the window is hidden should restore the window, or quit. A first-close hint
    ("Hypatia is still running in the tray") avoids confusion.
  - Tray menu: **Open Hypatia**, **Pair a device...**, remote-access status (LAN /
    Tailscale addresses, number of paired devices), **Quit** (stops the backend, as the
    current exit path does).
  - Optional setting, off by default: start at login, minimized to the tray
    (`launch_at_startup` package).
  - Platform notes. Windows: notification-area icon, works out of the box. macOS: a
    menu-bar icon; decide whether the Dock icon hides while the window is hidden. Linux:
    needs `libayatana-appindicator3` at build and run time, and GNOME needs the
    AppIndicator extension to show tray icons at all. Add the package to
    `build-desktop.yml`, include it in the AppImage, and note it in troubleshooting. If no
    tray is available, fall back to "closing quits".
  - The tray keeps the **process** alive, not the **machine**. Laptop sleep still makes
    the backend unreachable. Document this. A "prevent sleep while remote access is on"
    option is deferred.
  - Tests: the backend launcher's shutdown path must still run on Quit and on OS
    logout/shutdown, with no orphaned uvicorn processes.
- `cors_origin_regex` only affects browsers. It matters for the PWA option, not for native apps.

### 10.2 Authentication: device pairing tokens (not OAuth/JWT)

There's one user and no accounts, so OAuth and JWT refresh flows add complexity with no benefit.
Use opaque, revocable per-device tokens:

- New table `devices` (`id`, `name`, `token_hash`, `created_at`, `last_seen_at`,
  `revoked_at`) plus an Alembic migration. No `scope` column, since paired devices have
  full permissions. Decide whether backups exclude it (they probably should).
- **Pairing**: Settings > "Pair a device" calls `POST /api/devices/pairing-code` (local
  client only) and shows a QR code with `{"url", "code", "cert_sha256"}`. The code is
  single-use and expires after about 5 minutes. The phone calls `POST /api/devices/pair`
  with `{code, device_name}`, receives `token = secrets.token_urlsafe(32)` once, and the
  server stores only its SHA-256. Rate-limit the pair endpoint.
- **Desktop client auth**: the launcher generates a random local token per launch, passes
  it to the backend via an env var, and the desktop `ApiClient` sends it. Don't rely on
  "requests from 127.0.0.1 are trusted". `tailscale serve` or any local reverse proxy
  makes remote requests appear to come from loopback.
- **Enforcement**: a FastAPI dependency or middleware requires `Authorization: Bearer <token>`
  on every `/api/*` route and on the chat WebSocket, and leaves `/health` open. Native
  `web_socket_channel` (`IOWebSocketChannel.connect(url, headers: ...)`) can send headers.
  A web/PWA client can't, so it would need a `?token=` query parameter or a subprotocol.
- **Permissions: full access (decided 2026-10-19)**. A paired device can do everything the
  desktop client can: change settings and API keys, import and export backups, delete
  Classes and files, and pair or revoke devices. The one exception: the desktop's
  per-launch local token isn't a device, so it can't be revoked from a phone, and the
  desktop always keeps control.
  - Consequence: a lost or stolen unlocked phone, or a leaked token, has full control of
    Hypatia, including replacing API keys and deleting Classes. Mitigations: revoke from
    the desktop Settings or the tray menu; show last-seen time and IP per device; tokens
    stay in Keystore/Keychain via `flutter_secure_storage`. There's no in-app lock
    (decided 2026-10-19), so the phone's own lock screen is the only barrier.
  - API keys stay masked in `GET /api/settings` (`_mask_key`), so a phone can replace
    keys but never read them.
- New `ErrorCode`s such as `AUTH_REQUIRED`, `AUTH_INVALID`, and `PAIRING_CODE_INVALID`,
  following the existing `HypatiaError` pattern.
- Settings UI: list paired devices with last-seen time, and revoke them.

### 10.3 Transport security

A Bearer token over plain HTTP can be sniffed on shared Wi-Fi such as campus networks.
Options, roughly in order of preference:

1. **Tailscale or another WireGuard VPN**: encrypted, works off-LAN, and `tailscale cert`
   gives a real HTTPS certificate. Recommended for remote use. Hypatia only needs to bind
   to the Tailscale interface.
2. **Self-signed cert with pinning**: the backend generates a cert on first enable, and its
   SHA-256 goes into the pairing QR. The app's Dio/`HttpClient` uses
   `badCertificateCallback` to accept only that fingerprint. Uvicorn takes
   `--ssl-keyfile`/`--ssl-certfile`. `cryptography` is already a dependency.
3. Plain HTTP on a trusted home LAN: allowed, with a warning. It needs Android cleartext
   config and an iOS ATS exception (`NSAllowsLocalNetworking`).

**Decided (2026-10-19): support both LAN and Tailscale.** Concretely:

- The backend binds `0.0.0.0` when remote access is on, so it's reachable on both the LAN
  and the Tailscale interface. It serves **one** pinned self-signed certificate. Pinning
  compares fingerprints rather than hostnames, so the same cert works for the LAN IP and
  the Tailscale address. `tailscale cert` isn't needed, because a certificate valid only
  for the MagicDNS name would fail on the LAN IP.
- The desktop detects its addresses: LAN IPs from the network interfaces, the Tailscale IP
  (`100.64.0.0/10` range), and the MagicDNS name via `tailscale status --json` when the CLI
  is present. The pairing QR carries a list of URLs, for example
  `{"urls": ["https://192.168.1.20:8443", "https://desktop.tailnet-xyz.ts.net:8443"], "code", "cert_sha256"}`.
- The phone tries URLs in order (LAN first, since it's faster), remembers the last one
  that worked, and retries the list on failure. The connection banner shows which route
  is in use.
- Android: the Tailscale app must be connected on the phone, and Android allows only one
  active VPN, so it conflicts with other VPNs. The phone needs no Hypatia-specific
  Tailscale setup. Both devices just have to be on the same tailnet.
- Firewall: the first bind to `0.0.0.0` triggers the Windows Defender Firewall prompt.
  Document allowing it on private networks (and on the Tailscale interface). Never
  recommend allowing it on public networks.
- Desktop UI: Settings > Remote access shows the toggle, the port, the detected LAN and
  Tailscale URLs, "Pair a device" (QR), and the paired-device list.

### 10.4 Discovery (optional)

QR pairing already carries the URL. Optional mDNS advertisement (`_hypatia._tcp`) with
the Flutter `bonsoir` package would survive DHCP IP changes. Without it, a changed desktop
IP means re-scanning the QR code, or using the Tailscale MagicDNS name.

### 10.5 Make chat resilient to disconnects (bug)

`_handle_ask_stream` and the other handlers in `chat.py` save the assistant message only
after every chunk has been sent. If the socket drops mid-stream, `send_json` raises and the
answer is lost even though the LLM tokens were spent. Phones background apps constantly,
so this will happen often. Fix: keep generating when a send fails, always save the
assistant message, and have the client reload `/chat/history` on reconnect. Related bug:
the `message_id` in the `complete` frame is a fresh `uuid4()`, not the saved row's ID.

### 10.6 Offline-safe study endpoints

- `FlashcardReview` currently only takes `rating`, and the scheduler uses "now". Add
  optional `reviewed_at` (clamped: not in the future, not older than some limit such as
  30 days) and `client_review_id` (idempotency key, unique per card) so queued reviews can be
  replayed exactly once with correct intervals.
- When replaying, apply events per card in `reviewed_at` order. If the card has already been
  reviewed later on another client, apply the event anyway in arrival order and log it.
  For a single user that's acceptable, and it avoids a CRDT.
- Storage for idempotency: the schema has no review log today (`flashcards` holds only
  the current SM-2 state), so add a `flashcard_reviews` table (`id`, `card_id`,
  `client_review_id` unique, `rating`, `reviewed_at`, `received_at`) with an Alembic
  migration. Include it in backups (`routers/backup.py`) like the other study tables.
- Quiz attempts: MCQ, true/false, matching, and fill-in grading are deterministic and can run
  on the device, or be submitted later. Short-answer grading needs the LLM, so queue it and
  show it as "pending grading".
- Add a lightweight `GET /api/classes/{id}/study/snapshot` (decks + due cards + `due_at`
  values) so the app can fill its cache in one call. Optional; the existing endpoints work.

### 10.7 Uploads from mobile

- The upload endpoint takes a single multipart request of up to 3 GB. On mobile, iOS
  suspends Dio requests when the app goes to the background, and cellular uploads are slow.
  Options: keep the app in the foreground with a progress UI (`onSendProgress` is already
  wired up), or use `background_downloader`, which supports background uploads on iOS and
  Android. Chunked or resumable uploads are a stretch item.
- Consider warning before uploading large videos over cellular (`connectivity_plus`).

### 10.8 Contract and tests

- Update `docs/api-contract.yaml` and `schemas.py` (devices, pairing, auth errors, review fields).
- Tests: auth enforcement on every router (parametrize over the route table so new routes
  can't skip it), pairing expiry and reuse, revocation, WebSocket auth, review idempotency
  and `reviewed_at` clamping, and chat save-on-disconnect.
- The existing test clients need the local token. Add it in `tests/conftest.py` and
  `tests/e2e/conftest.py` so the suite keeps passing.

---

## 5. Frontend tasks (10B)

### 10.9 Add the platforms

- `flutter create --platforms=android,ios --org com.mattxgong --project-name hypatia .` in
  `frontend/`. The pubspec `name` is `frontend`, so set the IDs explicitly rather than relying
  on the generated defaults: Android `applicationId` and `namespace` set to
  `com.mattxgong.hypatia` in `android/app/build.gradle(.kts)`, and iOS
  `PRODUCT_BUNDLE_IDENTIFIER` set to `com.mattxgong.hypatia` in the Runner target. Commit
  `android/` and `ios/`.
- The ID is "at least initially". Changing it later makes it a different app: Android
  won't update in place, so the user uninstalls and reinstalls (losing the offline cache and
  pairing token, and re-pairing), and on iOS a new ID uses another of the free account's
  App ID slots. All real data lives on the desktop, so a change is cheap now and gets more
  annoying over time. Decide before sharing APKs with anyone else.
- Set Android `minSdk` and the iOS deployment target to the highest minimum required by
  the plugins (`pdfrx`, `media_kit`, `flutter_secure_storage`, `file_picker`), and confirm
  on the first build.
- Enable `android:`/`ios:` in the `flutter_launcher_icons` config (both are `false` now).
- `pubspec.yaml` `version: 0.2.0` has no build number. The stores need an increasing
  `versionCode`/`CFBundleVersion`, so pass `--build-number` in CI and keep `release.yml`'s
  tag-vs-pubspec check working.

### 10.10 Isolate desktop-only code

| Code | Issue on mobile | Action |
|---|---|---|
| `BackendLauncher` (spawns Python via `dart:io` `Process`) | Can't run on iOS, and is pointless on Android | Never construct it on mobile. Use the connection provider (10.11) for `baseUrl`. |
| `window_manager` in `main.dart` | Already behind `_isDesktop` | Keep the guard and check the import builds on mobile |
| `desktop_drop` `DropTarget` in `home_screen.dart` | Desktop/web plugin | Wrap it so it's used only on desktop |
| `media_kit_libs_windows_video` | Windows only | Switch to `media_kit_libs_video` (covers Android/iOS too), or add the per-platform libs |
| `/files/{id}/open` usage and "open in OS app" actions | No desktop file manager | Download to a temp dir, then use the share sheet or open in-app |
| Keyboard shortcuts / `Focus` handling | Harmless | Keep, but add touch alternatives for every shortcut |

### 10.11 Connection and onboarding

- First-run screen: "Connect to Hypatia on your computer". Scan the QR code
  (`mobile_scanner`, needs camera permission) or enter the URL and code manually.
- Store the URL, token, and cert fingerprint in `flutter_secure_storage` (already a
  dependency). iOS Keychain entries survive uninstall, so validate the token on first
  launch and clear it if it fails.
- A `connectionProvider` (Riverpod) owns `baseUrl` and status (`connected` /
  `desktopUnreachable` / `unauthorized`). `ApiClient` gets a Dio interceptor that adds
  `Authorization` and turns 401 into a re-pair prompt. `WebSocketService` passes the headers.
- Reconnect with backoff, and on `AppLifecycleState.resumed` (via `AppLifecycleListener`):
  reopen the chat socket, reload chat history (see 10.5), and resume task polling. Pause
  polling while the app is in the background.
- Show a clear "Desktop offline" banner while keeping cached study content usable.

### 10.12 Responsive layout

The 3-panel `Row` stays for expanded widths. Add Material 3 window-size classes:

- **Compact (< 600 dp, phones)**: a bottom `NavigationBar` with **Wiki / Chat / Study /
  Sources**. The class switcher goes in the `AppBar`. The wiki tree becomes a list screen
  that pushes page views (`go_router` is already a dependency). Search goes in the app bar.
  The source viewer opens full-screen. No drag dividers.
- **Medium (600-840 dp: tablets in portrait, foldables, large phones in landscape)**: two
  panes. Navigation goes in a `NavigationRail`. The primary pane holds the wiki tree and
  page; the secondary pane holds Chat, Study, or Sources, switched from the rail. A
  draggable split uses a touch-sized handle of at least 24 dp.
- **Expanded (>= 840 dp: tablets in landscape)**: the current 3-panel layout, with
  touch-friendly dividers (larger hit areas, no hover dependence) and the collapse
  buttons kept.
- **Tablets are first-class (decided 2026-10-19)**, which adds the following:
  - Size classes come from the **window** size, not the screen. Android split-screen and
    freeform windows can resize the app between compact and expanded at runtime, and state
    must survive that: the selected Class and page, chat draft, and review session belong in
    Riverpod providers, not widget state.
  - Rotation keeps place: reading position, the open flashcard, and quiz progress all survive.
  - Don't lock orientation. Leave `android:resizeableActivity` at its default (true).
  - Hardware keyboards and trackpads are common on tablets. The existing desktop shortcuts
    should work, and mouse hover affordances can stay when a pointer is present.
  - Side-by-side source viewer and wiki page on expanded tablets (citation tap opens the
    source in the other pane instead of full-screen).
  - Test matrix: phone 390x844, tablet portrait 800x1280, tablet landscape 1280x800, and a
    foldable around 673x841. Run it in widget tests and on at least one physical or
    emulated Android tablet.
- Android back gesture / predictive back: `PopScope` on nested navigation so back closes the
  page or sheet instead of exiting.
- Touch details: tap targets of at least 48 dp. Anything that currently relies on hover
  (tooltips, hover menus, resize handles) needs a tap or long-press equivalent. The chat
  input must stay above the keyboard (`resizeToAvoidBottomInset`, `SafeArea`). Wide
  `flutter_math_fork` equations and tables need horizontal scroll. Flashcard review gets
  large rating buttons, with swipe-to-rate as an optional extra.
- Widget tests at phone sizes (e.g. 390x844) and tablet sizes using `tester.view.physicalSize`.

### 10.13 Capture on mobile

- **Files**: `file_picker` works on mobile. On iOS it copies the picked file into the app's
  temp directory, so large videos take time and space before the upload starts.
- **Photos and camera** (`image_picker`): useful for whiteboards, slides, and printed
  handouts. MarkItDown doesn't do real OCR without an LLM or vision client, so this
  depends on 10.13a.
- **Audio recording** (`record` package, microphone permission): record a lecture and
  upload it, and the existing whisper pipeline transcribes it on the desktop. iOS needs the
  `audio` background mode if recording should continue with the screen locked.
- **Share to Hypatia**: receive files or URLs from other apps (`share_handler` or
  `receive_sharing_intent`). On iOS this needs a Share Extension target and an **App Group**.
  That's the only place an App Group is needed.

### 10.13a Local OCR in ingestion (backend, decided 2026-10-19)

Without OCR, a photographed page becomes an almost empty source. Add a local OCR step to
`file_converter.py` for image uploads. It's also worth applying to scanned PDFs that have
no text layer (it's cheap to include, and it helps desktop users too).

- **Engine candidates**. Evaluate on 15-20 real sample photos (whiteboard, slide on a
  projector, printed handout, phone photo at an angle, handwriting) before picking one:

  | Engine | Install | Notes |
  |---|---|---|
  | Tesseract (via `pytesseract` or subprocess) | **System binary**, like ffmpeg, plus language packs | Mature, good on clean print, weak on photos at an angle and on handwriting. Needs a setup step and packaging on all 3 OSes. |
  | RapidOCR (`rapidocr-onnxruntime`) | **pip only**, with small ONNX models bundled | No system install, so it fits `requirements.lock` and the bundled backend. Generally better than Tesseract on photographed and scene text. English plus Chinese models are the main ones. |
  | EasyOCR / PaddleOCR | pip, heavy (PyTorch / Paddle) | Large install size. Rejected unless the others fail. |

  Leaning: **RapidOCR** if its quality is comparable, because it adds no new system
  dependency for users, whereas Tesseract would be a second "install ffmpeg"-style
  prerequisite. Confirm that the license, wheel availability on Windows, macOS (arm64), and
  Linux, and the lockfile all work under `--universal --python-version 3.11`.
- **Handwriting**: none of the local engines handle handwriting well. Set expectations in
  the UI ("printed text works best"). A vision-LLM option for handwriting can come later.
- **Pipeline**: correct the EXIF orientation (Pillow), downscale very large photos (for
  example to a 2500 px long edge), optionally convert to grayscale, run OCR, then write
  the markdown (`converted/<file_id>.md`) with the OCR text plus a note that it's OCR
  output. Low-confidence lines can be dropped or marked. Then ingest as usual.
- **Graceful degradation**: if the engine is missing, store the image with a "text could
  not be extracted" note. Use a module-level availability flag like `_FFMPEG_AVAILABLE` in
  `video_processor.py`, and add a task warning.
- **Settings**: OCR language (default `en`). Nothing else until it's needed.
- **Tests**: golden-file tests with a few small committed fixture images; unit tests for
  rotation and downscaling; e2e coverage of upload image → converted markdown → wiki page.
- **Docs**: if Tesseract is chosen, update `CLAUDE.md` (setup reminder next to ffmpeg),
  `scripts/setup.sh`, `docs/troubleshooting.md`, and the master plan's Assumptions.

### 10.14 Offline study cache and review queue

- Keep it simple, per the "no speculative abstractions" rule. Store the snapshot of decks,
  due cards, and recently viewed wiki pages as JSON files under
  `getApplicationSupportDirectory()`, or in `sqflite`/`drift` if querying is needed.
  Don't mirror the server schema.
- Offline review: remove the card from the session as soon as it's rated, and append
  `{client_review_id, card_id, rating, reviewed_at}` to a persisted queue. Flush the queue
  in order on reconnect (10.6), then refresh the snapshot. No Dart port of SM-2 is needed
  unless next intervals should be shown offline.
- Offline quizzes: grade deterministic question types locally. Queue the attempt and any
  short-answer items for server grading.
- Mark cached content as stale when its `page_hashes` no longer match (the server already
  computes `out_of_date`).

### 10.15 Notifications (local, not FCM)

- `flutter_local_notifications`: schedule a daily "N cards due in <Class>" reminder at a
  user-chosen time, computed from cached `due_at`, and reschedule after each sync or review.
- Android 13+ requires the `POST_NOTIFICATIONS` runtime permission. Use inexact scheduling,
  because exact alarms (`SCHEDULE_EXACT_ALARM`) are restricted. iOS allows at most 64
  pending notifications, which is fine for one daily reminder per Class.
- "Ingestion finished" alerts would need real push, which requires an always-on server and
  APNs/FCM credentials, so they're out of scope for Option A. Show them on the next app open.
- Background sync (`workmanager` / iOS `BGAppRefreshTask`) is best-effort, and iOS may never
  run it. Don't build features that depend on it. Sync on app open and resume is enough.

---

## 6. Platform configuration

### 6.1 Android (`AndroidManifest.xml` / resources)

- `INTERNET` (release builds don't include it by default).
- `CAMERA` and `RECORD_AUDIO` only if 10.13 capture ships. `POST_NOTIFICATIONS` for 10.15.
- No storage permissions: `file_picker` uses the Storage Access Framework.
- `network_security_config.xml`: allow cleartext only if plain-HTTP LAN mode (10.3 option 3)
  is supported. For the pinned self-signed cert, trust is handled in Dart instead.

### 6.2 iOS (`Info.plist`): deferred, Android first

- `NSLocalNetworkUsageDescription`: required. iOS 14+ shows a local-network prompt the first
  time the app contacts a LAN address. If the user denies it, connections fail silently,
  so detect that and explain it.
- `NSBonjourServices` (`_hypatia._tcp`) only if mDNS discovery (10.4) ships.
- `NSAppTransportSecurity` > `NSAllowsLocalNetworking = true` for LAN HTTP. Don't use
  `NSAllowsArbitraryLoads`.
- `NSCameraUsageDescription` (QR scanning and photos), `NSPhotoLibraryUsageDescription`,
  and `NSMicrophoneUsageDescription`, each only if the feature ships.
- `ITSAppUsesNonExemptEncryption = false` (standard TLS only), which skips the export
  compliance prompt.
- `UIBackgroundModes`: `audio` only if background recording ships. Nothing else is needed.

### 6.3 Distribution without the stores

- **Android**: a signed APK attached to GitHub Releases (sideloading) works today and needs
  no Play account. Google's planned developer-verification requirement for sideloaded apps
  (rolling out from 2026) may require registering the signing identity, so check before release.
- **iOS**: there's no general sideloading (EU alternative marketplaces aside). For personal
  use, a free Apple ID can run builds that expire after 7 days. A paid account
  ($99/year) gives TestFlight (builds last 90 days, needs a lighter beta review) or the App Store.

### 6.4 Store review risks (Option A specifically): out of scope while distribution is personal-only

- **Reviewers can't use a companion app without the desktop.** Apple 2.1 (completeness) and
  4.2 (minimum functionality) rejections are likely unless you provide a demo mode with
  bundled sample Class data, or a reachable demo backend, with instructions in the
  review notes. Plan for this from the start.
- A privacy policy URL is required by both stores. Apple privacy labels and the Play Data
  safety form must describe the data flow: phone to the user's own computer to the LLM
  provider the user picked.
- Monetization (IAP, subscriptions) is out of scope. If it ever happens, digital features
  must use the stores' billing systems, and the rules vary by region.

### 6.5 iOS without a Mac: xtool research (2026-10-19)

iOS is deferred (Android first), but building for iOS normally requires a Mac. I looked
at **xtool** (<https://github.com/xtool-org/xtool>) as a way around that.

**What xtool is.** It's an MIT-licensed "cross-platform Xcode replacement" for Linux, WSL,
and macOS. The latest release is 1.22.2 (2026-10-14), and the project is active (about
12.7k stars). It:
- builds **SwiftPM packages** into iOS apps (`xtool new`, `xtool dev`),
- signs and installs apps, and manages devices (`xtool install <ipa>`, `uninstall`,
  `launch`, `devices`),
- talks to Apple Developer Services (`xtool ds`, `xtool auth`), and offers the `XKit`
  library,
- supports Foundation-style app extensions (widgets, share extensions) via `xtool.yml`.
  ExtensionKit isn't supported yet.

**Setup on this Windows machine** (from its Linux/Windows install guide):
1. WSL2, plus **usbipd-win** to pass the iPhone's USB connection into WSL. If you get
   `AFCClient.Error.muxError`, the guide links a workaround that relays the device
   through iTunes on Windows.
2. A Swift 6.4 toolchain for Linux, plus `usbmuxd` (`libimobiledevice-utils` is handy too).
3. Download **Xcode 27 `.xip`** from developer.apple.com in a browser, with an Apple ID.
   xtool extracts an iOS SDK from it; Xcode itself never runs.
4. Install the `xtool` AppImage, then run `xtool setup`. Login mode is either an
   **App Store Connect API key** (paid program, public API, recommended) or an
   **Apple ID password** (works with free accounts, but uses private Apple APIs, so the
   docs suggest a throwaway Apple ID).

**The catch: xtool can't build Hypatia's Flutter app.**
- It only builds SwiftPM packages. Flutter's iOS side is an Xcode project
  (`ios/Runner.xcodeproj`) whose plugins are partly still CocoaPods-based.
- Release iOS builds need Dart AOT compilation (`gen_snapshot` for iOS), which Flutter
  only ships for macOS hosts.
- Flutter, Compose, and React Native support is an open feature request (issue #28). An
  earlier request (#36) was closed without adding it.
- What xtool **can** do for Hypatia is **sign and install an `.ipa` built elsewhere**.
  An open PR (#284) mentions installing a Flutter app with a widget extension this way.

**Mac-free iOS pipelines, in order of preference:**

| Pipeline | How | Pros | Cons |
|---|---|---|---|
| **A. CI build + xtool install (recommended to try first)** | A GitHub Actions `macos` runner runs `flutter build ios --release --no-codesign`, zips `Runner.app` into `Payload/` as an `.ipa` artifact, then on Windows/WSL: `xtool install Hypatia.ipa` with the iPhone on USB | Uses Flutter's supported toolchain; xtool only signs and installs; no Mac to own | No hot reload or debugger, and every change is a CI round trip. Flutter debug (JIT) builds can't launch standalone on iOS, so it has to be release or profile builds. macOS runner minutes are free on public repos, but private repos consume minutes at a 10x multiplier. **Verify early**: that `xtool install` re-signs an unsigned IPA with your team (the README says "sign and install", but I didn't confirm this exact flow). |
| B. xcross (<https://github.com/arxdeus/xcross>) | Reimplements Flutter's iOS build pipeline in Dart. It builds, signs, installs, and hot-reloads from Windows/Linux using the SDK from `Xcode.xip`, and credits xtool as a source | A real dev loop with hot reload, and no Mac at all | Small project (about 110 stars) that relies on undocumented Apple protocols. AGPL-3.0 (applies to the tool itself). Needs Swift 6.4+, LLVM, Python with `pymobiledevice3`, and iOS 17+ devices. Release/AOT on Windows/Linux uses a third-party `gen_snapshot`. CocoaPods-only plugins get skipped. Try it for development; don't depend on it for releases. |
| C. A Mac (borrowed, used Mac mini, or a cloud Mac) | Standard Xcode workflow | Fully supported, with debugging and simulators | Cost and hardware. |

**Apple account limits** (they apply to xtool and xcross alike):
- **Free Apple ID**: apps expire after **7 days** and must be reinstalled; at most **3**
  sideloaded apps per device; a small weekly cap on new App IDs. That's workable for
  personal use (the decided distribution), but it means a reinstall every week.
- App Groups: xtool currently **filters App Groups out on free teams**, and open PR #284
  would allow one per app. The iOS **Share Extension** (10.13) needs an App Group, so on a
  free account, defer it until that PR lands or a paid account is used. Local notifications
  (10.15) work fine on free accounts. Push isn't used.
- **Paid ($99/year)**: 1-year profiles, App Groups, TestFlight, and API-key login (the
  public API, so no throwaway-account risk).

**Plan for when iOS starts:**
1. Add an iOS job to CI (`flutter build ios --release --no-codesign`) early, even before
   iOS is a target. That catches plugin incompatibilities (`media_kit` needs
   `media_kit_libs_ios_video`; check `pdfrx`, `file_picker`, `flutter_secure_storage`,
   `mobile_scanner`, `record`).
2. Proof of concept for pipeline A: CI-built IPA, then `xtool install` from WSL on a free
   Apple ID (decided), launched on the device. The repo is public, so the macOS runner
   minutes are free. The unsigned IPA has no secrets, so it can be a normal workflow
   artifact. Signing happens locally with xtool, so no Apple credentials ever go into
   GitHub. If re-signing doesn't work, try xcross next. A paid account would be the last
   resort, and would reverse the free-account decision.
3. Ship iOS without the Share Extension (free account: no App Groups). Revisit once xtool
   PR #284 or an equivalent lands. Then add the extension as a separate target built on
   the macOS runner, with xtool only signing it.
4. Weekly routine on a free account: re-run `xtool install` (or `xtool dev`) before the
   7-day profile expires. The app's data lives on the desktop, so an expired app only
   loses the offline cache.
5. Then do §6.2 (`Info.plist` keys), the local-network permission UX, and widget tests at
   iPhone and iPad sizes.

---

## 7. CI and release (10C)

- `ci.yml`: add a `flutter build apk --debug` job (ubuntu), so Android breakage is caught on
  every PR. Add `flutter build ios --no-codesign` (macos runner) when iOS work starts.
  `flutter analyze` and `flutter test` already cover shared code.
- `build-desktop.yml` stays desktop-only. Add a reusable `build-android.yml` called by
  `manual.yml` and `release.yml`, which builds a signed release APK and attaches it
  (plus its SHA-256 in `SHA256SUMS.txt`) to the GitHub Release.
- Android signing: a release keystore stored as a base64 repository secret plus the key
  password secrets. Keep an offline backup of the keystore. If it's lost, existing installs
  can't be updated in place.
- **Public repo (decided 2026-10-19)**:
  - Only sign in workflows that run on `v*` tags or `workflow_dispatch` (`release.yml`,
    `manual.yml`). PR CI builds unsigned debug APKs. Workflows triggered from forks don't get
    secrets, and must never use `pull_request_target` with a checkout of the PR code.
  - Keep `*.jks`, `key.properties`, and `local.properties` in `.gitignore`. Decode the
    keystore to a temp path in CI, and never echo it to logs.
  - The release APK and its SHA-256 are public on GitHub Releases. That's fine, because the
    app has no secrets: pairing tokens are created per device at pairing time.
  - macOS runner minutes are free, so an iOS `--no-codesign` build job can run on every PR
    without extra cost (§6.5 step 1).
- Deferred: iOS signing (certificate and provisioning profile, TestFlight upload) and Play
  App Signing.
- Update `CLAUDE.md` (repo structure, how to run on a device:
  `flutter run -d <device> --dart-define=HYPATIA_BACKEND_URL=...`), `README`, and
  `docs/troubleshooting.md` (local network permission, firewall rules for the backend port,
  Tailscale setup).

---

## 8. Effort (rough, solo developer, Option A)

| Work | Estimate |
|---|---|
| 10A backend: remote mode, pairing/auth, TLS, LAN + Tailscale URLs, chat-disconnect fix, review fields, tests | 2-3 weeks |
| 10.1 system tray (3 desktop OSes, Linux packaging) | 3-5 days |
| 10.13a local OCR (engine evaluation + pipeline + tests) | 1 week |
| 10B platforms, desktop-code isolation, connection/onboarding | 1 week |
| 10B responsive layout: compact + first-class medium/expanded tablet layouts | 3-4 weeks |
| 10B offline study cache, queue, notifications | 1 week |
| 10B capture (camera/audio/Android share intent) | 1 week |
| 10C Android CI job, signed APK in releases | 2-4 days |
| **Total (Android phones + tablets, personal distribution)** | **~10-13 weeks** |
| Later: iOS (CI build + xtool install PoC, plist, permissions UX; Share Extension later) | +1-2 weeks (§6.5) |
| Later: public store listings (demo mode, privacy policy, review) | +1-2 weeks |

Out-of-pocket costs for the decided scope: $0. Tailscale's personal tier is free. The
Apple ($99/year) and Google Play ($25 one-time) accounts are only needed for the later items.

The ordering, parallel tracks, and milestones are in §9.

---

## 9. Implementation plan: ordering and parallelism

Planning only. Nothing here has been started. This section breaks Phase 10 into work
items, their dependencies, the parallel tracks, and milestone gates. It assumes one
developer, possibly helped by agents working in separate git worktrees. "Parallel" means
the items have no dependency on each other and touch mostly different files, so they can
be separate branches or PRs that merge in any order.

### 9.1 Work items and dependencies

Tasks are split where one part can start much earlier than the rest (for example,
10.13a's evaluation vs. its implementation).

| ID | Work item | Area | Depends on | Size |
|---|---|---|---|---|
| W1 | 10.5 chat save-on-disconnect + `message_id` fix | backend | none | 1-2 d |
| W2 | 10.6 review fields, `flashcard_reviews` table + migration, backup inclusion | backend | none | 2-3 d |
| W3 | 10.13a step 1: OCR engine evaluation (scratch script, sample photos, no app code) | backend (spike) | none | 1-2 d |
| W4 | 10.13a step 2: OCR in `file_converter.py`, graceful degradation, tests | backend | W3 | 3-4 d |
| W5 | 10.2 auth: `devices` table + migration, `get_principal()` dependency on all routes + WS, local per-launch token (launcher + desktop `ApiClient`), pairing endpoints, error codes, test fixtures | backend + desktop client | none | 4-6 d |
| W6 | 10.1a remote-access settings: `remote_access_enabled`, host/port, launcher binds `0.0.0.0` only when enabled, restart flow | backend + launcher | W5 (never bind beyond loopback without auth) | 1-2 d |
| W7 | 10.3 TLS: self-signed cert generation, uvicorn SSL args, fingerprint; LAN + Tailscale address detection; QR payload | backend + desktop UI | W5, W6 | 3-4 d |
| W8 | Desktop "Remote access" settings UI: toggle, URLs, pairing QR, device list + revoke | desktop UI | W5 (API), W7 (QR contents) | 2-3 d |
| W9 | 10.1b system tray + close-to-tray (only while remote access is on), Linux packaging | desktop | W6 (needs the setting) | 3-5 d |
| W10 | 10.9 add Android/iOS platforms with `com.mattxgong.hypatia`, icons, build number | mobile platform | none | 1 d |
| W11 | 10C-early: CI `flutter build apk --debug` (ubuntu) + `flutter build ios --release --no-codesign` (macOS, free on the public repo) | CI | W10 | 1 d |
| W12 | 10.10 isolate desktop-only code (launcher, `DropTarget`, `media_kit` libs, `/open`) | frontend | W10 | 1-2 d |
| W13 | 10.12a responsive shell: size classes, compact bottom nav, medium rail + 2 panes, go_router/back handling | frontend (shared UI) | none (built and tested on desktop by resizing the window, plus widget tests) | 1.5-2 wk |
| W14 | 10.12b screen-by-screen adaptation: wiki tree/page, chat (keyboard insets), study, source viewer, sheets, touch targets | frontend (shared UI) | W13 | 1-1.5 wk |
| W15 | 10.12c tablet polish: expanded touch dividers, side-by-side source viewer, rotation/resize state, keyboard/trackpad, test matrix | frontend | W14 | 3-5 d |
| W16 | 10.11a connection layer: `connectionProvider`, Dio auth interceptor, WS headers, cert pinning, URL fallback list, reconnect on resume | frontend | W12, W5 (auth contract), W7 (pinning) | 3-4 d |
| W17 | 10.11b onboarding UI: QR scan (`mobile_scanner`), manual entry, "desktop offline" banner, re-pair on 401 | frontend | W16, W8 (a QR to scan) | 2-3 d |
| W18 | 10.14 offline study cache + review queue + local quiz grading | frontend | W2, W16 | 4-5 d |
| W19 | 10.15 local due-card notifications | frontend | W18, W10 | 2 d |
| W20 | 10.13 capture: file/photo/camera picker, audio recording, Android share intent | frontend | W16; camera is only worth releasing after W4 | 4-5 d |
| W21 | 10.7 mobile uploads: progress UI, `background_downloader`, cellular warning | frontend | W16, W20 | 2-3 d |
| W22 | 10C-release: `build-android.yml`, keystore secrets, signed APK + SHA-256 on tag | CI | W11 | 1-2 d |
| W23 | Docs: `CLAUDE.md`, README, troubleshooting (firewall, Tailscale, tray on GNOME, OCR) | docs | lands with each item; final pass at the end | 1 d |
| W24 | (Optional) 10.4 mDNS discovery | both | W7, W17 | 2 d |

Phase 11 work folded in (see [11-study-and-ux.md](./11-study-and-ux.md), "Ordering
relative to Phase 10"):
- Before W2 and W13: Phase 11 wave A (11.1-11.5). It changes `quiz_questions` (W2 and
  10.14 snapshot study data) and restyles `home_screen.dart` (W13 splits it into layouts).
- With W14: 11.6 suggested replies and 11.7 `@` references, so the chat input is designed
  once for keyboard and touch.
- With W9: 11.8 crash-safe jobs, since a backend that lives in the tray runs for days.

10.8 (contract and tests) isn't a separate item. Each backend item updates
`docs/api-contract.yaml`, `schemas.py`, and its tests in the same PR, as the repo
conventions require.

### 9.2 Dependency graph

```
No dependencies (start any time):
    W1 chat fix    W2 review log    W3 OCR eval    W10 platforms    W13 responsive shell

Backend/desktop:   W5 auth ──> W6 remote mode ──> W7 TLS + URLs ──> W8 desktop pairing UI
                                    └──> W9 tray
                   W3 ──> W4 OCR in ingestion

Mobile platform:   W10 ──> W11 CI build jobs ──> W22 signed release
                   W10 ──> W12 isolate desktop code

Shared UI:         W13 ──> W14 screens ──> W15 tablet polish

Integration:       W12 + W5 + W7 ──> W16 connection layer ──> W17 onboarding (+W8)
                   W16 + W2      ──> W18 offline study ──> W19 notifications
                   W16 (+W4)     ──> W20 capture ──> W21 mobile uploads
```

**Critical path** (longest chain): W5 → W6 → W7 → W16 → W17 → W18 → W19 → release, about
4.5-5.5 weeks. W13 → W14 → W15 (the responsive layout, about 3-4 weeks) runs alongside it
and is the second-longest chain. Starting W13 on day 1 keeps it off the critical path.

### 9.3 Parallel tracks

| Track | Items, in order | Mostly touches |
|---|---|---|
| **A: Backend security** | W5 → W6 → W7 → W8 → W9 | `backend/app/` (`dependencies.py`, `config.py`, `main.py`, a new devices router/service), `backend_launcher.dart`, `api_client.dart` (local token), settings screen, `main.dart` (tray) |
| **B: Backend independent** | W1, W2, W3 → W4 | `routers/chat.py`, `routers/study.py`, `services/study/`, `routers/backup.py`, `services/file_converter.py` |
| **C: Shared UI** | W13 → W14 → W15 | `screens/home_screen.dart`, `widgets/**`, routing |
| **D: Mobile platform** | W10 → W11 → W12, then W16 → W17 → W18 → W19 → W20 → W21, then W22 | `frontend/android/`, `frontend/ios/`, `.github/workflows/`, new connection service/provider, `providers/` |

Tracks A, B, C, and the first part of D (W10-W12) can all run at the same time. The second
part of D is integration, and it waits on A (W5, W7) and B (W2).

### 9.4 Merge conflict hotspots: serialize these

Parallel branches will collide in a few places. Agree on an order, or keep these edits
small and rebase often:

- **Alembic migrations**: Phase 11's 11.2 (`quiz_questions.points`) and 11.8 (`jobs`) add
  revisions too. 11.2 lands before Phase 10 starts. 11.8 lands with W9, so order it against
  W2 and W5 the same way. W2 (`flashcard_reviews`) and W5 (`devices`) both add revisions
  off the same head (currently `f4b2c8d6e1a3_add_study_tables`, unless a newer one lands
  first). If both branches are open at once, the second to merge must rebase its
  `down_revision` onto the first. Add a CI check that `alembic heads` shows exactly one
  head. Simplest is to merge W2 before W5's migration is generated.
- **`frontend/lib/services/api_client.dart`**: W5 (local token header), W16 (auth
  interceptor, base URL from the connection provider), W18 (queued review calls). Do W5's
  change minimally (one header), and let W16 restructure it.
- **`frontend/lib/main.dart`**: W9 (tray, prevent-close), W12 (platform guards), W17
  (onboarding route). Land W12 early, since it's small.
- **`frontend/lib/screens/home_screen.dart`**: W12 (wrap `DropTarget`) and W13 (layout
  rewrite). Do W12's wrap first, or fold it into W13.
- **`docs/api-contract.yaml` / `schemas.py`**: W1, W2, W5, W7. These are additive
  sections, so conflicts are textual and easy, but they're frequent.
- **`backend/tests/conftest.py` + `tests/e2e/conftest.py`**: W5 changes every test client
  (auth token). Branches that add tests before W5 merges will need the fixture after rebasing.

### 9.5 Milestones and gates

Each milestone ends with the full CI check set green (`ruff`, `mypy`, `pytest`,
`flutter analyze`, `dart format`, `flutter test`, plus the new Android/iOS build jobs).

| Milestone | Contents | Gate: done when... | Cumulative (2 tracks / solo serial) |
|---|---|---|---|
| **M0 Foundations** | W1, W2, W3, W10, W11, W12; W13 started | A dropped WebSocket mid-`/ask` still saves the answer. Replayed reviews are idempotent. An OCR engine is chosen and recorded in §10. Debug APK and unsigned iOS build pass in CI. The desktop app is unchanged. | ~1.5 wk / ~2 wk |
| **M1 Secure remote backend** | W5, W6, W7, W8, W9 | With remote access off, nothing changes (loopback only). With it on, a request from another machine without a token gets 401, a paired token works over HTTPS with the pinned cert, revoking cuts access immediately, and closing the window goes to the tray. | ~3.5 wk / ~5 wk |
| **M2 First phone connection** | W16, W17 (W13 continuing) | An Android phone pairs by QR, connects over LAN and over Tailscale (switching routes when Wi-Fi drops), browses the wiki, and chats with streaming. Backgrounding mid-answer and resuming shows the saved answer. | ~4.5 wk / ~6.5 wk |
| **M3 Phone and tablet layouts** | W14, W15 | All screens are usable at 390x844, 800x1280, and 1280x800; rotation and split-screen keep state; the widget-test matrix passes. | ~6 wk / ~9 wk |
| **M4 Offline study** | W18, W19 | In airplane mode: review due cards and take a quiz (deterministic grading). On reconnect the queue flushes exactly once, and intervals match an online review. A daily "cards due" notification fires. | ~6.5 wk / ~10 wk |
| **M5 Capture** | W4, W20, W21 | A photographed printed page becomes a wiki source with readable text. A recorded lecture is transcribed on the desktop. Sharing a PDF from another app uploads it. A large video upload shows progress and survives backgrounding. | ~7.5 wk / ~11.5 wk |
| **M6 v1 release (Android)** | W22, W23 (W24 optional) | Tagging `v*` publishes a signed APK + SHA-256. A fresh install → pair → use works by following the docs alone. | ~8 wk / ~12 wk |
| **Later: iOS** | §6.5 steps 2-5 | CI-built IPA installed via `xtool install` on a free Apple ID, and the app works without the Share Extension. | +1-2 wk |

The two-track column assumes tracks A/B and C/D run concurrently (for example, you on one,
an agent in a worktree on another). Solo serial work matches the §8 estimate.

M3 and M4 don't depend on each other. If the layout work runs long, M4 can be done first
on the compact layout alone.

### 9.6 Suggested first two weeks

- **Days 1-2**: W1 (a small bug fix that also benefits desktop users now), W10, then W11,
  so the mobile builds are guarded in CI from the start.
- **Days 2-4**: W2 and W3 alongside W12. Start W13 (the long pole) on desktop, using widget
  tests at phone sizes.
- **Day 5 on**: W5, the riskiest backend change because every route and test changes. Keep
  it in one PR with an exhaustive route-coverage test. Merge W2's migration first (§9.4).
- **Week 2**: W6 → W7 → W8, with W13 continuing in parallel. Decide the OCR engine (W3
  outcome) and record it in §10.

### 9.7 Risks to the ordering

- **W5 touches everything.** Keeping it isolated and merged early means later branches
  rebase onto the auth fixtures once, not repeatedly.
- **The xtool re-sign proof of concept** isn't on the Android path. Run it any time after
  W11 produces an unsigned IPA, so iOS feasibility is known early without blocking Android.
- **OCR evaluation (W3) might find no engine is good enough.** Then camera capture ships
  as "images only" in M5, and W20's other parts (audio, share intent) aren't affected.
- **Responsive layout (W13-W15) is the most likely to overrun.** If it slips, M2 and M4
  can still be tested on a phone with the compact layout alone. Tablet polish (W15) is the
  safest piece to finish last.

---

## 10. Open questions

Resolved 2026-10-18: backend model (companion now, hosted later), platforms (Android
first), distribution (personal use), and v1 scope (read + chat, offline study, capture,
notifications).
Resolved 2026-10-19: remote reach (LAN + Tailscale), device permissions (full), desktop
lifetime (system tray), image OCR (local engine), tablets (first-class), doc location
(moved and linked). See Decisions at the top.

Still open:

1. **PWA**: still worth pursuing, now that native Android distribution is decided? (Probably not.)
2. **OCR engine**: RapidOCR (pip only) vs Tesseract (system binary). Decide after the
   sample-photo evaluation in 10.13a.
3. **Final app identifier**: keep `com.mattxgong.hypatia` permanently? Confirm before
   sharing APKs beyond your own devices (see 10.9).

Resolved 2026-10-19 (second round): close-to-tray only while remote access is on, no
in-app lock, public repo, free Apple ID for iOS, `com.mattxgong.hypatia` as the initial
app identifier.

---

## References

- Flutter adaptive design: https://docs.flutter.dev/ui/adaptive-responsive
- Material 3 window size classes: https://m3.material.io/foundations/layout/applying-layout/window-size-classes
- `web_socket_channel`: https://pub.dev/packages/web_socket_channel
- `flutter_secure_storage`: https://pub.dev/packages/flutter_secure_storage
- `mobile_scanner`: https://pub.dev/packages/mobile_scanner
- `flutter_local_notifications`: https://pub.dev/packages/flutter_local_notifications
- `background_downloader`: https://pub.dev/packages/background_downloader
- `share_handler`: https://pub.dev/packages/share_handler
- `bonsoir`: https://pub.dev/packages/bonsoir
- `media_kit`: https://pub.dev/packages/media_kit
- Tailscale HTTPS certificates: https://tailscale.com/kb/1153/enabling-https
- xtool: https://github.com/xtool-org/xtool (docs: https://xtool.sh; Linux/Windows install guide in `Documentation/xtool.docc/Installation-Linux.md`)
- xtool issue #28 (Flutter/RN/CMP support): https://github.com/xtool-org/xtool/issues/28
- xtool PR #284 (App Groups on free teams): https://github.com/xtool-org/xtool/pull/284
- xcross (Flutter iOS builds from Windows/Linux): https://github.com/arxdeus/xcross
- Discussion of xtool's Flutter limitations: https://news.hada.io/topic?id=20982
- `tray_manager`: https://pub.dev/packages/tray_manager
- `launch_at_startup`: https://pub.dev/packages/launch_at_startup
- RapidOCR: https://github.com/RapidAI/RapidOCR
- Tesseract: https://github.com/tesseract-ocr/tesseract
- usbipd-win (USB passthrough to WSL): https://learn.microsoft.com/en-us/windows/wsl/connect-usb
- Apple App Review Guidelines: https://developer.apple.com/app-store/review/guidelines/
- Apple local network privacy: https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy
- Android Storage Access Framework: https://developer.android.com/training/data-storage/shared/documents-files
- Android notification permission: https://developer.android.com/develop/ui/views/notifications/notification-permission
