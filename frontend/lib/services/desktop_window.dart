import 'dart:async';
import 'dart:ui' show AppExitResponse;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tray_manager/tray_manager.dart';
import 'package:window_manager/window_manager.dart';

import '../widgets/remote/remote_access_dialog.dart';
import 'backend_launcher.dart';

/// What closing the window does.
enum CloseAction {
  /// Stop the backend and exit, as when remote access is off.
  quit,

  /// Keep running in the tray so paired phones stay connected.
  hide,

  /// Keep running, but stay in the taskbar or dock: GNOME without the
  /// AppIndicator extension shows no tray icon, so a hidden window couldn't
  /// be brought back.
  minimize,
}

CloseAction closeAction({
  required bool remoteAccessOn,
  required bool trayShown,
  required TargetPlatform platform,
}) {
  if (!remoteAccessOn || !trayShown) return CloseAction.quit;
  return platform == TargetPlatform.linux
      ? CloseAction.minimize
      : CloseAction.hide;
}

/// The tray menu's entries, by key.
@visibleForTesting
Menu trayMenu(RemoteAccess access) => Menu(
  items: [
    MenuItem(key: 'open', label: 'Open Hypatia'),
    MenuItem(key: 'pair', label: 'Pair a device...'),
    MenuItem.separator(),
    MenuItem(
      key: 'status',
      label: 'Phones can connect on port ${access.port}',
      disabled: true,
    ),
    MenuItem.separator(),
    MenuItem(key: 'quit', label: 'Quit Hypatia'),
  ],
);

const _hintShownKey = 'hypatia_tray_hint_shown';

/// Owns the desktop window's lifetime: stops the backend before the app exits,
/// and while remote access is on keeps Hypatia running in the system tray when
/// the window closes, so paired phones stay connected.
///
/// Flutter desktop doesn't dispose the widget tree when the window closes, so
/// this hooks the window close (window_manager), app quit requests such as
/// Cmd+Q (AppLifecycleListener), and the tray (tray_manager).
class DesktopWindow with WindowListener, TrayListener {
  DesktopWindow(this._launcher, this._prefs, this._navigatorKey);

  final BackendLauncher _launcher;
  final SharedPreferences _prefs;

  /// For dialogs started from the tray menu.
  final GlobalKey<NavigatorState> _navigatorKey;

  Future<void>? _shutdown;
  bool _trayShown = false;
  // Held so the listeners stay registered for the app's lifetime.
  AppLifecycleListener? _lifecycle;
  StreamSubscription<BackendStatus>? _status;

  void install() {
    unawaited(windowManager.setPreventClose(true));
    windowManager.addListener(this);
    trayManager.addListener(this);
    _lifecycle = AppLifecycleListener(
      onExitRequested: () async {
        await _stopOnce();
        return AppExitResponse.exit;
      },
    );
    // The remote-access setting takes effect with each backend start.
    _status = _launcher.onStatusChange.listen((status) {
      if (status == BackendStatus.ready) unawaited(_syncTray());
    });
  }

  Future<void> _syncTray() async {
    final access = _launcher.remoteAccess;
    if (access.enabled) {
      try {
        await trayManager.setIcon(
          defaultTargetPlatform == TargetPlatform.windows
              ? 'assets/app_icon/tray.ico'
              : 'assets/app_icon/app_icon.png',
        );
        await trayManager.setToolTip('Hypatia: phones can connect');
        await trayManager.setContextMenu(trayMenu(access));
        _trayShown = true;
      } catch (e) {
        // No tray on this desktop: closing the window quits instead.
        debugPrint('Tray unavailable: $e');
        _trayShown = false;
      }
    } else if (_trayShown) {
      await trayManager.destroy();
      _trayShown = false;
      // Without the tray, a hidden window would be unreachable.
      if (!await windowManager.isVisible()) await _open();
    }
  }

  Future<void> _open() async {
    await windowManager.show();
    await windowManager.focus();
  }

  Future<void> _stopOnce() => _shutdown ??= () async {
    try {
      await _launcher.stopBackend().timeout(const Duration(seconds: 10));
    } catch (_) {
      // Exit anyway; the backend also exits when its stdin pipe closes.
    }
  }();

  Future<void> _quit() async {
    await _stopOnce();
    await _status?.cancel();
    _lifecycle?.dispose();
    if (_trayShown) await trayManager.destroy();
    await windowManager.destroy();
  }

  /// Says once, before the first hide, where Hypatia went.
  Future<void> _hintOnce() async {
    if (_prefs.getBool(_hintShownKey) ?? false) return;
    unawaited(_prefs.setBool(_hintShownKey, true));
    final context = _navigatorKey.currentContext;
    if (context == null || !context.mounted) return;
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Hypatia keeps running'),
        content: const Text(
          'Remote access is on, so Hypatia stays running in the system tray '
          'to keep your phones connected. Open it or quit from the tray icon.',
        ),
        actions: [
          FilledButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Got it'),
          ),
        ],
      ),
    );
  }

  @override
  Future<void> onWindowClose() async {
    switch (closeAction(
      remoteAccessOn: _launcher.remoteAccess.enabled,
      trayShown: _trayShown,
      platform: defaultTargetPlatform,
    )) {
      case CloseAction.quit:
        await _quit();
      case CloseAction.hide:
        await _hintOnce();
        await windowManager.hide();
      case CloseAction.minimize:
        await _hintOnce();
        await windowManager.minimize();
    }
  }

  @override
  void onTrayIconMouseDown() => unawaited(_open());

  @override
  void onTrayIconRightMouseDown() => unawaited(trayManager.popUpContextMenu());

  @override
  void onTrayMenuItemClick(MenuItem menuItem) {
    switch (menuItem.key) {
      case 'open':
        unawaited(_open());
      case 'pair':
        unawaited(() async {
          await _open();
          final context = _navigatorKey.currentContext;
          if (context != null && context.mounted) {
            await showRemoteAccessDialog(context);
          }
        }());
      case 'quit':
        unawaited(_quit());
    }
  }
}
