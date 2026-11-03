import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../../config/theme.dart';
import '../../models/device.dart';
import '../../models/paired_desktop.dart';
import '../../providers/backend_provider.dart';
import '../../providers/remote_access_provider.dart';
import '../../services/api_client.dart';
import '../../services/backend_launcher.dart';
import '../common/error_card.dart';

Future<void> showRemoteAccessDialog(BuildContext context) => showDialog<void>(
  context: context,
  builder: (_) => const RemoteAccessDialog(),
);

/// "5 minutes ago", "3 hours ago", "on 2026-10-30".
String describeLastSeen(DateTime at, DateTime now) {
  final ago = now.difference(at);
  if (ago.inMinutes < 1) return 'just now';
  if (ago.inMinutes < 60) {
    return '${ago.inMinutes} minute${ago.inMinutes == 1 ? '' : 's'} ago';
  }
  if (ago.inHours < 24) {
    return '${ago.inHours} hour${ago.inHours == 1 ? '' : 's'} ago';
  }
  final day = at.toIso8601String().substring(0, 10);
  return 'on $day';
}

/// What the pairing QR encodes: JSON with the URLs, code and fingerprint.
String pairingQrData(PairingCode code) => jsonEncode(code.qrPayload);

/// "K7MQ2XRP" as "K7MQ-2XRP", easier to read out and type.
String formatPairingCode(String code) =>
    code.length == 8 ? '${code.substring(0, 4)}-${code.substring(4)}' : code;

/// Settings > Remote access: let phones connect, pair them, revoke them.
class RemoteAccessDialog extends ConsumerStatefulWidget {
  const RemoteAccessDialog({super.key});

  @override
  ConsumerState<RemoteAccessDialog> createState() => _RemoteAccessDialogState();
}

class _RemoteAccessDialogState extends ConsumerState<RemoteAccessDialog> {
  PairingCode? _code;
  int _devicesWhenIssued = 0;
  Timer? _tick;
  bool _issuing = false;

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  Future<void> _issueCode() async {
    setState(() => _issuing = true);
    try {
      final code = await ref.read(apiClientProvider).createPairingCode();
      if (!mounted) return;
      _devicesWhenIssued =
          ref.read(pairedDevicesProvider).valueOrNull?.length ?? 0;
      setState(() => _code = code);
      // A countdown, and a look for the newly paired device every few seconds.
      _tick?.cancel();
      var ticks = 0;
      _tick = Timer.periodic(const Duration(seconds: 1), (_) {
        if (!mounted) return;
        if (++ticks % 3 == 0) ref.invalidate(pairedDevicesProvider);
        setState(() {});
      });
    } on ApiException catch (e) {
      _snack('Could not create a pairing code: ${e.detail}');
    } finally {
      if (mounted) setState(() => _issuing = false);
    }
  }

  void _stopCode() {
    _tick?.cancel();
    _tick = null;
    setState(() => _code = null);
  }

  Future<void> _setEnabled(BackendLauncher launcher, bool enabled) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(
          enabled ? 'Let phones connect?' : 'Stop phones connecting?',
        ),
        content: Text(
          enabled
              ? 'Hypatia restarts its backend to listen on your network. '
                    'Windows may ask to allow it through the firewall: allow '
                    'it on private networks only.'
              : 'Hypatia restarts its backend. Paired phones stay paired and '
                    'reconnect when you turn this back on.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Restart backend'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    // The startup screen replaces the app while the backend restarts, so
    // close this dialog first.
    Navigator.of(context).pop();
    await launcher.setRemoteAccess(
      RemoteAccess(enabled: enabled, port: launcher.remoteAccess.port),
    );
  }

  Future<void> _revoke(Device device) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Revoke ${device.name}?'),
        content: const Text(
          'It is disconnected at once and has to be paired again to connect.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Revoke'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ref.read(apiClientProvider).revokeDevice(device.id);
      ref.invalidate(pairedDevicesProvider);
    } on ApiException catch (e) {
      _snack('Could not revoke ${device.name}: ${e.detail}');
    }
  }

  void _snack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final launcher = ref.watch(backendLauncherProvider);
    final status = ref.watch(remoteAccessStatusProvider);
    final devices = ref.watch(pairedDevicesProvider);

    // A phone paired with the code on screen: done with it.
    final count = devices.valueOrNull?.length;
    if (_code != null && count != null && count > _devicesWhenIssued) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _code != null) {
          _stopCode();
          _snack('Device paired.');
        }
      });
    }

    final enabled = status.valueOrNull?.enabled ?? false;
    // Only a backend this app started can be restarted with new settings.
    final canToggle = launcher != null && launcher.externalBaseUrl == null;

    return AlertDialog(
      title: const Text('Remote access'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Let phones and tablets connect'),
                subtitle: Text(
                  canToggle
                      ? 'Over an encrypted connection on port '
                            '${launcher.remoteAccess.port}, on your home '
                            'network or your Tailscale network.'
                      : 'Set this where the backend was started.',
                ),
                value: enabled,
                onChanged: canToggle && status.hasValue
                    ? (value) => _setEnabled(launcher, value)
                    : null,
              ),
              if (status.hasError)
                ErrorCard(
                  error: status.error!,
                  compact: true,
                  onRetry: () => ref.invalidate(remoteAccessStatusProvider),
                ),
              if (status.valueOrNull case final s? when s.enabled) ...[
                const SizedBox(height: 8),
                Text('Addresses', style: theme.textTheme.labelLarge),
                const SizedBox(height: 4),
                if (s.urls.isEmpty)
                  const Text('No network address found. Check the connection.')
                else
                  for (final url in s.urls) SelectableText(url),
                const SizedBox(height: 16),
                _pairing(theme),
              ],
              const Divider(height: 32),
              Text('Paired devices', style: theme.textTheme.labelLarge),
              const SizedBox(height: 4),
              devices.when(
                loading: () => const Padding(
                  padding: EdgeInsets.all(8),
                  child: Center(child: CircularProgressIndicator()),
                ),
                error: (e, _) => ErrorCard(
                  error: e,
                  compact: true,
                  onRetry: () => ref.invalidate(pairedDevicesProvider),
                ),
                data: (list) => list.isEmpty
                    ? const Text('No devices yet.')
                    : Column(
                        children: [
                          for (final device in list)
                            ListTile(
                              contentPadding: EdgeInsets.zero,
                              leading: const Icon(Icons.smartphone_outlined),
                              title: Text(device.name),
                              subtitle: Text(_seen(device)),
                              trailing: TextButton(
                                onPressed: () => _revoke(device),
                                child: const Text('Revoke'),
                              ),
                            ),
                        ],
                      ),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }

  String _seen(Device device) {
    final at = device.lastSeenAt;
    if (at == null) return 'Not connected yet';
    final from = device.lastSeenIp == null ? '' : ' from ${device.lastSeenIp}';
    return 'Last seen ${describeLastSeen(at, DateTime.now())}$from';
  }

  Widget _pairing(ThemeData theme) {
    final code = _code;
    if (code == null) {
      return Align(
        alignment: Alignment.centerLeft,
        child: FilledButton.icon(
          onPressed: _issuing ? null : _issueCode,
          icon: const Icon(Icons.qr_code_2, size: 18),
          label: const Text('Pair a device'),
        ),
      );
    }
    final left = code.expiresAt.difference(DateTime.now());
    if (left.isNegative) {
      return Row(
        children: [
          const Expanded(child: Text('The code expired.')),
          FilledButton(onPressed: _issueCode, child: const Text('New code')),
        ],
      );
    }
    final seconds = left.inSeconds;
    return Column(
      children: [
        Text(
          'Scan with the Hypatia app on your phone, or type one of the '
          'addresses above and this code.',
          style: theme.textTheme.bodyMedium,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 12),
        // Dark modules on white whatever the theme, so every scanner reads it.
        DecoratedBox(
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: HypatiaTokens.corners,
          ),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: QrImageView(
              data: pairingQrData(code),
              size: 220,
              backgroundColor: Colors.white,
              semanticsLabel: 'Pairing QR code',
            ),
          ),
        ),
        const SizedBox(height: 12),
        SelectableText(
          formatPairingCode(code.code),
          style: theme.textTheme.headlineSmall?.copyWith(
            fontFeatures: const [FontFeature.tabularFigures()],
            letterSpacing: 2,
          ),
        ),
        Text(
          'Expires in ${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}',
          style: theme.textTheme.bodySmall,
        ),
        // A phone given the code by hand checks this before pairing.
        if (code.certSha256 case final cert?) ...[
          const SizedBox(height: 8),
          Text(
            'Fingerprint ${shortFingerprint(cert)}',
            style: theme.textTheme.bodySmall?.copyWith(fontFamily: 'monospace'),
          ),
        ],
        const SizedBox(height: 8),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            TextButton.icon(
              onPressed: () {
                Clipboard.setData(ClipboardData(text: code.code));
                _snack('Code copied.');
              },
              icon: const Icon(Icons.copy, size: 16),
              label: const Text('Copy code'),
            ),
            TextButton(onPressed: _stopCode, child: const Text('Done')),
          ],
        ),
      ],
    );
  }
}
