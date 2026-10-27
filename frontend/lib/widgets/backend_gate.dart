import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../providers/backend_provider.dart';
import '../services/backend_launcher.dart';

/// Shows [child] (the app's router) once the backend is ready, and the
/// startup or problem screen until then. Used as `MaterialApp.builder`, so the
/// screens share the app's theme; the router isn't built, and so makes no API
/// calls, until the backend can answer them.
class BackendGate extends ConsumerWidget {
  const BackendGate({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(backendStatusProvider);
    switch (status) {
      case BackendStatus.ready:
        return child;
      case BackendStatus.error:
      case BackendStatus.crashed:
        return _BackendProblemScreen(status: status);
      default:
        return _BackendLoadingScreen(status: status);
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

class _BackendProblemScreen extends ConsumerWidget {
  const _BackendProblemScreen({required this.status});

  final BackendStatus status;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final launcher = ref.watch(backendLauncherProvider);
    final log = ref.watch(backendLogProvider);
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
              'Python 3.11 or newer is required. See the log below for details.',
              style: Theme.of(context).textTheme.bodyLarge,
            ),
            const SizedBox(height: 16),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                FilledButton.icon(
                  onPressed: launcher == null
                      ? null
                      : () => unawaited(launcher.retryBackend()),
                  icon: const Icon(Icons.refresh),
                  label: const Text('Retry'),
                ),
                OutlinedButton.icon(
                  onPressed: launcher == null
                      ? null
                      : () => _selectPython(context, launcher),
                  icon: const Icon(Icons.folder_open),
                  label: const Text('Select Python'),
                ),
                OutlinedButton.icon(
                  onPressed: () => _copyDiagnostics(context, launcher, log),
                  icon: const Icon(Icons.copy),
                  label: const Text('Copy Diagnostics'),
                ),
                TextButton.icon(
                  onPressed: () => unawaited(
                    launchUrl(
                      Uri.parse(
                        'https://github.com/mattxgong/Hypatia/blob/main/docs/troubleshooting.md',
                      ),
                      mode: LaunchMode.externalApplication,
                    ),
                  ),
                  icon: const Icon(Icons.open_in_new),
                  label: const Text('Troubleshooting'),
                ),
              ],
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

  Future<void> _selectPython(
    BuildContext context,
    BackendLauncher launcher,
  ) async {
    final isWindows = defaultTargetPlatform == TargetPlatform.windows;
    final file = await FilePicker.pickFile(
      type: isWindows ? FileType.custom : FileType.any,
      allowedExtensions: isWindows ? const ['exe'] : null,
      dialogTitle: 'Select Python 3.11 or newer',
    );
    final path = file?.path;
    if (path == null) return;

    final accepted = await launcher.selectPython(path);
    if (!context.mounted) return;
    if (!accepted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Select a Python 3.11 or newer executable.'),
        ),
      );
      return;
    }
    unawaited(launcher.retryBackend());
  }

  Future<void> _copyDiagnostics(
    BuildContext context,
    BackendLauncher? launcher,
    List<String> log,
  ) async {
    final diagnostics = [
      'Hypatia backend startup diagnostics',
      'Platform: ${defaultTargetPlatform.name}',
      'Status: ${status.name}',
      'Backend URL: ${launcher?.baseUrl}',
      '',
      ...log,
    ].join('\n');
    await Clipboard.setData(ClipboardData(text: diagnostics));
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Diagnostics copied to clipboard.')),
    );
  }
}
