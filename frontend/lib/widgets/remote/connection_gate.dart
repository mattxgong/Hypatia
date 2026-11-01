import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/connection_provider.dart';
import '../../providers/foreground_provider.dart';
import '../../services/websocket_service.dart';

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
    return switch (status) {
      ConnectionStatus.connected => widget.child,
      ConnectionStatus.unpaired => const _UnpairedScreen(),
      ConnectionStatus.unauthorized => const _UnauthorizedScreen(),
      ConnectionStatus.desktopUnreachable => _UnreachableScreen(
        connection: connection,
      ),
      ConnectionStatus.checking ||
      ConnectionStatus.connecting => const _ConnectingScreen(),
    };
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
    return Material(
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
    );
  }
}

class _GateScreen extends StatelessWidget {
  const _GateScreen({
    required this.icon,
    required this.title,
    required this.body,
    this.actions = const [],
  });

  final IconData icon;
  final String title;
  final String body;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: Column(
                mainAxisSize: MainAxisSize.min,
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

class _UnpairedScreen extends StatelessWidget {
  const _UnpairedScreen();

  @override
  Widget build(BuildContext context) {
    return const _GateScreen(
      icon: Icons.phonelink_outlined,
      title: 'Connect to Hypatia on your computer',
      body:
          'Your wiki, chat and study material live on your computer. On it, '
          'open Hypatia, then Remote access, and turn on "Let phones and '
          'tablets connect". Pairing by scanning its QR code comes in the '
          'next update.',
    );
  }
}

class _UnreachableScreen extends ConsumerWidget {
  const _UnreachableScreen({required this.connection});

  final RemoteConnection connection;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final addresses = connection.desktop?.urls.join('\n') ?? '';
    return _GateScreen(
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

class _UnauthorizedScreen extends ConsumerWidget {
  const _UnauthorizedScreen();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return _GateScreen(
      icon: Icons.link_off,
      title: 'This phone needs pairing again',
      body:
          'Your computer no longer accepts this phone. It may have been '
          'removed under Remote access there.',
      actions: [
        FilledButton(
          onPressed: () => ref.read(connectionProvider.notifier).forget(),
          child: const Text('Pair again'),
        ),
      ],
    );
  }
}
