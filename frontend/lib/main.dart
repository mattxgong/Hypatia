import 'dart:async';
import 'dart:ui' show AppExitResponse;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit/media_kit.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:window_manager/window_manager.dart';

import 'app.dart';
import 'providers/backend_provider.dart';
import 'providers/theme_provider.dart';
import 'services/backend_launcher.dart';

const _externalBackendUrl = String.fromEnvironment('HYPATIA_BACKEND_URL');
const _externalApiToken = String.fromEnvironment('HYPATIA_API_TOKEN');

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  MediaKit.ensureInitialized();

  BackendLauncher? launcher;
  if (_isDesktop) {
    launcher = BackendLauncher(
      externalBaseUrl: _externalBackendUrl,
      externalApiToken: _externalApiToken,
    );
    await windowManager.ensureInitialized();
    const windowOptions = WindowOptions(
      size: Size(1280, 800),
      minimumSize: Size(900, 600),
      center: true,
      title: 'Hypatia',
    );
    await windowManager.waitUntilReadyToShow(windowOptions, () async {
      await windowManager.show();
      await windowManager.focus();
    });
    _BackendShutdown(launcher).install();
  }

  final prefs = await SharedPreferences.getInstance();
  final container = ProviderContainer(
    overrides: [
      sharedPreferencesProvider.overrideWithValue(prefs),
      backendLauncherProvider.overrideWithValue(launcher),
    ],
  );
  // Subscribe to the launcher before it starts so no status or log line is
  // missed.
  container.read(backendStatusProvider);
  container.read(backendLogProvider);

  runApp(
    UncontrolledProviderScope(container: container, child: const HypatiaApp()),
  );
  if (launcher != null) unawaited(launcher.startBackend());
}

bool get _isDesktop =>
    !kIsWeb &&
    (defaultTargetPlatform == TargetPlatform.windows ||
        defaultTargetPlatform == TargetPlatform.macOS ||
        defaultTargetPlatform == TargetPlatform.linux);

/// Stops the backend before the app exits. Flutter desktop doesn't dispose
/// the widget tree when the window closes, so this hooks the window close
/// (window_manager) and app quit requests such as Cmd+Q (AppLifecycleListener).
class _BackendShutdown with WindowListener {
  _BackendShutdown(this._launcher);

  final BackendLauncher _launcher;
  Future<void>? _shutdown;
  // Held so the listener stays registered for the app's lifetime.
  AppLifecycleListener? _lifecycle;

  void install() {
    unawaited(windowManager.setPreventClose(true));
    windowManager.addListener(this);
    _lifecycle = AppLifecycleListener(
      onExitRequested: () async {
        await _stopOnce();
        return AppExitResponse.exit;
      },
    );
  }

  Future<void> _stopOnce() => _shutdown ??= () async {
    try {
      await _launcher.stopBackend().timeout(const Duration(seconds: 10));
    } catch (_) {
      // Exit anyway; the backend also exits when its stdin pipe closes.
    }
  }();

  @override
  Future<void> onWindowClose() async {
    await _stopOnce();
    _lifecycle?.dispose();
    await windowManager.destroy();
  }
}
