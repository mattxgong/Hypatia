import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../config/theme.dart';
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

/// The startup steps, in order. A first launch spends minutes installing the
/// backend's packages, so the screen shows where it is and what it's doing
/// rather than a bare spinner.
const _startupSteps = [
  (BackendStatus.discoveringPython, 'Find Python'),
  (BackendStatus.settingUpEnvironment, 'Set up the backend environment'),
  (BackendStatus.starting, 'Start the backend'),
];

class _BackendLoadingScreen extends ConsumerStatefulWidget {
  const _BackendLoadingScreen({required this.status});

  final BackendStatus status;

  @override
  ConsumerState<_BackendLoadingScreen> createState() =>
      _BackendLoadingScreenState();
}

class _BackendLoadingScreenState extends ConsumerState<_BackendLoadingScreen> {
  bool _showLog = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final log = ref.watch(backendLogProvider);
    final current = _startupSteps.indexWhere((s) => s.$1 == widget.status);

    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Starting Hypatia', style: theme.textTheme.titleLarge),
                const SizedBox(height: 16),
                for (final (i, (_, label)) in _startupSteps.indexed)
                  _StartupStep(
                    label: label,
                    state: current < 0 || i > current
                        ? _StepState.pending
                        : i < current
                        ? _StepState.done
                        : _StepState.active,
                  ),
                if (widget.status == BackendStatus.settingUpEnvironment)
                  Padding(
                    padding: const EdgeInsets.only(left: 32, top: 4),
                    child: Text(
                      'The first launch installs packages and can take a few '
                      'minutes.',
                      style: theme.textTheme.bodySmall,
                    ),
                  ),
                if (log.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  Semantics(
                    liveRegion: true,
                    child: Text(
                      log.last,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodySmall?.copyWith(
                        fontFamily: 'monospace',
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                  TextButton.icon(
                    onPressed: () => setState(() => _showLog = !_showLog),
                    icon: Icon(
                      _showLog ? Icons.expand_less : Icons.expand_more,
                    ),
                    label: Text(_showLog ? 'Hide details' : 'Show details'),
                  ),
                  if (_showLog) SizedBox(height: 240, child: _LogView(log)),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

enum _StepState { pending, active, done }

class _StartupStep extends StatelessWidget {
  const _StartupStep({required this.label, required this.state});

  final String label;
  final _StepState state;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final icon = switch (state) {
      _StepState.done => Icon(
        Icons.check_circle,
        size: 20,
        color: StatusColors.of(context).success,
      ),
      _StepState.active => const SizedBox.square(
        dimension: 20,
        child: Padding(
          padding: EdgeInsets.all(2),
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      ),
      _StepState.pending => Icon(
        Icons.radio_button_unchecked,
        size: 20,
        color: theme.colorScheme.outline,
      ),
    };
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          icon,
          const SizedBox(width: 12),
          Text(
            label,
            style: state == _StepState.pending
                ? theme.textTheme.bodyMedium?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  )
                : theme.textTheme.bodyMedium,
          ),
        ],
      ),
    );
  }
}

/// The backend's output, newest at the bottom.
class _LogView extends StatelessWidget {
  const _LogView(this.log);

  final List<String> log;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(8),
      color: Colors.black87,
      child: ListView.builder(
        reverse: true,
        itemCount: log.length,
        itemBuilder: (context, index) => Text(
          log[log.length - 1 - index],
          style: const TextStyle(
            color: Colors.white,
            fontFamily: 'monospace',
            fontSize: 12,
          ),
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
            Expanded(child: _LogView(log)),
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
