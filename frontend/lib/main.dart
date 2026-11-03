import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit/media_kit.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:window_manager/window_manager.dart';

import 'app.dart';
import 'providers/backend_provider.dart';
import 'providers/connection_provider.dart';
import 'providers/theme_provider.dart';
import 'services/backend_launcher.dart';
import 'services/desktop_window.dart';
import 'utils/platform.dart';

const _externalBackendUrl = String.fromEnvironment('HYPATIA_BACKEND_URL');
const _externalApiToken = String.fromEnvironment('HYPATIA_API_TOKEN');

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  MediaKit.ensureInitialized();

  BackendLauncher? launcher;
  if (isDesktop) {
    launcher = BackendLauncher(
      externalBaseUrl: _externalBackendUrl,
      externalApiToken: _externalApiToken,
    );
    await windowManager.ensureInitialized();
    const windowOptions = WindowOptions(
      size: Size(1280, 800),
      // Narrow enough for the phone and tablet layouts, which a narrowed
      // window switches to.
      minimumSize: Size(360, 560),
      center: true,
      title: 'Hypatia',
    );
    await windowManager.waitUntilReadyToShow(windowOptions, () async {
      await windowManager.show();
      await windowManager.focus();
    });
  }

  final prefs = await SharedPreferences.getInstance();
  if (launcher != null) {
    DesktopWindow(launcher, prefs, rootNavigatorKey).install();
  }
  final container = ProviderContainer(
    overrides: [
      sharedPreferencesProvider.overrideWithValue(prefs),
      backendLauncherProvider.overrideWithValue(launcher),
      // Phones and tablets reach a paired desktop's backend instead.
      remoteClientProvider.overrideWithValue(launcher == null),
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
