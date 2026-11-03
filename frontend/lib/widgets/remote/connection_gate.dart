import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/connection_provider.dart';
import '../../providers/foreground_provider.dart';
import '../../services/websocket_service.dart';
import 'pairing_screen.dart';

/// On a phone: shows [child] (the app) once the paired desktop answers, and
/// the pairing or connection screens until then. After the first connection
/// the app stays on screen if the desktop drops off, under a banner, so
/// nothing open is lost.
///
/// Also follows the app's lifecycle: polling pauses in the background, and
/// coming back re-checks the route and reopens the chat socket at once.
class ConnectionGate extends ConsumerStatefulWidget {
  const ConnectionGate({super.key, required this.child});

  final Widget child;

  @override
  ConsumerState<ConnectionGate> createState() => _ConnectionGateState();
}

class _ConnectionGateState extends ConsumerState<ConnectionGate> {
  late final AppLifecycleListener _lifecycle;

  @override
  void initState() {
    super.initState();
    _lifecycle = AppLifecycleListener(
      onHide: () => ref.read(appInForegroundProvider.notifier).state = false,
      onShow: () => ref.read(appInForegroundProvider.notifier).state = true,
      onResume: () => unawaited(_resume()),
    );
  }

  @override
  void dispose() {
    _lifecycle.dispose();
    super.dispose();
  }

  Future<void> _resume() async {
    ref.read(appInForegroundProvider.notifier).state = true;
    await ref.read(connectionProvider.notifier).resume();
    if (mounted) ref.read(webSocketServiceProvider).reconnectNow();
  }

  @override
  Widget build(BuildContext context) {
    final connection = ref.watch(connectionProvider);
    final status = connection.status;
    final blocked =
        status == ConnectionStatus.unpaired ||
        status == ConnectionStatus.unauthorized;
    if (connection.hasConnected && !blocked) {
      return Column(
        children: [
          _OfflineBanner(connection: connection),
          Expanded(child: widget.child),
        ],
      );
    }
    if (status == ConnectionStatus.connected) return widget.child;
    final screen = switch (status) {
      ConnectionStatus.unpaired => const PairingScreen(),
      ConnectionStatus.unauthorized => const PairingScreen(again: true),
      ConnectionStatus.desktopUnreachable => _UnreachableScreen(
        connection: connection,
      ),
      _ => const _ConnectingScreen(),
    };
    // These screens stand in for the app's router, so give them the
    // navigator and overlay text fields need.
    return Navigator(
      pages: [MaterialPage<void>(key: const ValueKey('gate'), child: screen)],
      onDidRemovePage: (_) {},
    );
  }
}

/// A strip over the app while the desktop is out of reach. Built (empty) even
/// when connected, so the app below keeps its place in the tree.
class _OfflineBanner extends ConsumerWidget {
  const _OfflineBanner({required this.connection});

  final RemoteConnection connection;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (connection.status == ConnectionStatus.connected) {
      return const SizedBox.shrink();
    }
    final theme = Theme.of(context);
    final retrying = connection.status == ConnectionStatus.connecting;
    return Semantics(
      liveRegion: true,
      child: Material(
        color: theme.colorScheme.errorContainer,
        child: SafeArea(
          bottom: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 8, 4),
            child: Row(
              children: [
                Icon(
                  Icons.cloud_off_outlined,
                  size: 18,
                  color: theme.colorScheme.onErrorContainer,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    retrying
                        ? 'Reconnecting to your computer…'
                        : "Can't reach your computer. Retrying.",
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onErrorContainer,
                    ),
                  ),
                ),
                TextButton(
                  onPressed: retrying
                      ? null
                      : () => ref.read(connectionProvider.notifier).probe(),
                  child: const Text('Retry'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The layout of the screens shown before the app: an icon, a title and an
/// explanation, then [children] (fields) and [actions] (buttons), centered.
/// With [onBack], a back button steps back within the flow.
class GateScreen extends StatelessWidget {
  const GateScreen({
    super.key,
    required this.icon,
    required this.title,
    required this.body,
    this.children = const [],
    this.actions = const [],
    this.onBack,
  });

  final IconData icon;
  final String title;
  final String body;
  final List<Widget> children;
  final List<Widget> actions;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: onBack == null
          ? null
          : AppBar(
              leading: IconButton(
                icon: const BackButtonIcon(),
                tooltip: MaterialLocalizations.of(context).backButtonTooltip,
                onPressed: onBack,
              ),
            ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(icon, size: 56, color: theme.colorScheme.primary),
                  const SizedBox(height: 16),
                  Text(
                    title,
                    style: theme.textTheme.headlineSmall,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 12),
                  Text(
                    body,
                    style: theme.textTheme.bodyMedium,
                    textAlign: TextAlign.center,
                  ),
                  if (children.isNotEmpty) ...[
                    const SizedBox(height: 24),
                    ...children,
                  ],
                  if (actions.isNotEmpty) ...[
                    const SizedBox(height: 24),
                    Wrap(
                      spacing: 12,
                      runSpacing: 8,
                      alignment: WrapAlignment.center,
                      children: actions,
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ConnectingScreen extends StatelessWidget {
  const _ConnectingScreen();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text('Connecting to Hypatia on your computer…'),
          ],
        ),
      ),
    );
  }
}

class _UnreachableScreen extends ConsumerWidget {
  const _UnreachableScreen({required this.connection});

  final RemoteConnection connection;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final addresses = connection.desktop?.urls.join('\n') ?? '';
    return GateScreen(
      icon: Icons.cloud_off_outlined,
      title: "Can't reach your computer",
      body:
          'Check that Hypatia is open on your computer with Remote access on, '
          'and that this phone is on the same network or Tailscale. Tried:\n'
          '$addresses',
      actions: [
        FilledButton(
          onPressed: () => ref.read(connectionProvider.notifier).probe(),
          child: const Text('Try again'),
        ),
        TextButton(
          onPressed: () => ref.read(connectionProvider.notifier).forget(),
          child: const Text('Forget this computer'),
        ),
      ],
    );
  }
}

/// On a phone: which computer it's paired with, and a way to unpair, after
/// which the pairing screen shows (to pair with another computer, say).
Future<void> showPairedComputerDialog(BuildContext context) => showDialog<void>(
  context: context,
  builder: (context) => const _PairedComputerDialog(),
);

class _PairedComputerDialog extends ConsumerWidget {
  const _PairedComputerDialog();

  Future<void> _forget(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Forget this computer?'),
        content: const Text(
          'This phone disconnects and has to be paired again, with this '
          'computer or another. To stop the computer accepting it as well, '
          'revoke it under Remote access there.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Forget'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    Navigator.of(context).pop();
    await ref.read(connectionProvider.notifier).forget();
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final connection = ref.watch(connectionProvider);
    final desktop = connection.desktop;
    return AlertDialog(
      title: const Text('Your computer'),
      content: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              connection.status == ConnectionStatus.connected
                  ? 'Connected at ${connection.url}'
                  : 'Not connected right now.',
            ),
            if (desktop != null) ...[
              const SizedBox(height: 12),
              Text('Addresses', style: theme.textTheme.labelLarge),
              for (final url in desktop.urls) SelectableText(url),
              const SizedBox(height: 12),
              Text(
                'Paired as "${desktop.deviceName}"',
                style: theme.textTheme.bodySmall,
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => _forget(context, ref),
          child: const Text('Forget this computer'),
        ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }
}
