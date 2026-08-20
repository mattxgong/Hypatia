import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:window_manager/window_manager.dart';

import 'app.dart';
import 'providers/theme_provider.dart';
import 'services/backend_launcher.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  if (_isDesktop) {
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
  }

  final prefs = await SharedPreferences.getInstance();

  runApp(
    ProviderScope(
      overrides: [sharedPreferencesProvider.overrideWithValue(prefs)],
      child: const HypatiaApp(),
    ),
  );
}

bool get _isDesktop =>
    !kIsWeb &&
    (defaultTargetPlatform == TargetPlatform.windows ||
        defaultTargetPlatform == TargetPlatform.macOS ||
        defaultTargetPlatform == TargetPlatform.linux);

class HypatiaApp extends StatelessWidget {
  const HypatiaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      title: 'Hypatia',
      debugShowCheckedModeBanner: false,
      home: BackendGate(),
    );
  }
}

class BackendGate extends StatefulWidget {
  const BackendGate({super.key});

  @override
  State<BackendGate> createState() => _BackendGateState();
}

class _BackendGateState extends State<BackendGate> {
  late final BackendLauncher _launcher;
  StreamSubscription<BackendStatus>? _statusSub;
  StreamSubscription<String>? _logSub;
  BackendStatus _status = BackendStatus.stopped;
  final List<String> _log = [];

  @override
  void initState() {
    super.initState();
    _launcher = BackendLauncher();

    if (!_isDesktop) {
      _status = BackendStatus.ready;
      return;
    }

    _statusSub = _launcher.onStatusChange.listen((status) {
      if (mounted) setState(() => _status = status);
    });
    _logSub = _launcher.onLog.listen((line) {
      _log.add(line);
      if (_log.length > 200) _log.removeAt(0);
    });
    unawaited(_launcher.startBackend());
  }

  @override
  void dispose() {
    _statusSub?.cancel();
    _logSub?.cancel();
    if (_isDesktop) {
      unawaited(_launcher.stopBackend());
    }
    _launcher.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    switch (_status) {
      case BackendStatus.ready:
        return const HypatiaShell();
      case BackendStatus.error:
      case BackendStatus.crashed:
        return _BackendProblemScreen(status: _status, log: _log);
      default:
        return _BackendLoadingScreen(status: _status);
    }
  }
}

class _BackendLoadingScreen extends StatelessWidget {
  const _BackendLoadingScreen({required this.status});

  final BackendStatus status;

  String get _message {
    switch (status) {
      case BackendStatus.discoveringPython:
        return 'Locating Python...';
      case BackendStatus.settingUpEnvironment:
        return 'Setting up backend environment...';
      case BackendStatus.starting:
        return 'Starting backend...';
      default:
        return 'Starting Hypatia...';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const CircularProgressIndicator(),
            const SizedBox(height: 24),
            Text(_message),
          ],
        ),
      ),
    );
  }
}

class _BackendProblemScreen extends StatelessWidget {
  const _BackendProblemScreen({required this.status, required this.log});

  final BackendStatus status;
  final List<String> log;

  @override
  Widget build(BuildContext context) {
    final title = status == BackendStatus.crashed
        ? 'Backend crashed'
        : 'Failed to start backend';

    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Something went wrong while starting the Hypatia backend. '
              'See the log below for details.',
              style: Theme.of(context).textTheme.bodyLarge,
            ),
            const SizedBox(height: 16),
            Expanded(
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(8),
                color: Colors.black87,
                child: ListView(
                  children: [
                    for (final line in log)
                      Text(
                        line,
                        style: const TextStyle(
                          color: Colors.white,
                          fontFamily: 'monospace',
                          fontSize: 12,
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
