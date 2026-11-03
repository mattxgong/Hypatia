import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../models/paired_desktop.dart';
import '../../providers/connection_provider.dart';
import '../../services/connection_store.dart';
import 'connection_gate.dart';

/// The camera view that reads the pairing QR, calling back with each code's
/// text. Tests replace it, since the camera is a platform plugin.
typedef QrScannerBuilder =
    Widget Function(BuildContext context, ValueChanged<String> onText);

final qrScannerProvider = Provider<QrScannerBuilder>(
  (ref) =>
      (context, onText) => _CameraScanner(onText: onText),
);

/// What a phone calls itself on the desktop's list of paired devices, until
/// the user names it.
String defaultDeviceName(TargetPlatform platform, Size screen) {
  final tablet = screen.shortestSide >= 600;
  return switch (platform) {
    TargetPlatform.iOS => tablet ? 'iPad' : 'iPhone',
    TargetPlatform.android => tablet ? 'Android tablet' : 'Android phone',
    _ => 'This device',
  };
}

enum _Step { choose, scan, enter, confirm }

/// Pairs this phone with Hypatia on a computer: scan the QR the desktop shows
/// under Remote access, or type its address and the code. A typed code has no
/// QR to carry the certificate's fingerprint, so the user checks it against
/// the one the desktop shows before the code is sent.
///
/// With [again], the phone was paired but the desktop no longer accepts it.
class PairingScreen extends ConsumerStatefulWidget {
  const PairingScreen({super.key, this.again = false});

  final bool again;

  @override
  ConsumerState<PairingScreen> createState() => _PairingScreenState();
}

class _PairingScreenState extends ConsumerState<PairingScreen>
    with WidgetsBindingObserver {
  final _name = TextEditingController();
  final _address = TextEditingController();
  final _code = TextEditingController();
  var _step = _Step.choose;
  var _busy = false;
  String? _error;
  String? _scanHint;

  // A typed code, waiting for its fingerprint to be checked.
  String? _origin;
  String? _typedCode;
  String? _fingerprint;

  bool get _canScan =>
      defaultTargetPlatform == TargetPlatform.android ||
      defaultTargetPlatform == TargetPlatform.iOS;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_name.text.isEmpty) {
      _name.text = defaultDeviceName(
        defaultTargetPlatform,
        MediaQuery.sizeOf(context),
      );
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _name.dispose();
    _address.dispose();
    _code.dispose();
    super.dispose();
  }

  /// Android's Back steps back through the flow. These screens stand in for
  /// the app's router, so no route would see it.
  @override
  Future<bool> didPopRoute() async {
    if (_step == _Step.choose || _busy) return false;
    _back();
    return true;
  }

  void _back() => setState(() {
    _step = _step == _Step.confirm ? _Step.enter : _Step.choose;
    _scanHint = null;
  });

  String get _deviceName {
    final name = _name.text.trim();
    return name.isEmpty
        ? defaultDeviceName(defaultTargetPlatform, MediaQuery.sizeOf(context))
        : name;
  }

  void _onScanned(String text) {
    if (_step != _Step.scan) return;
    final PairingPayload payload;
    try {
      payload = PairingPayload.parse(text);
    } on FormatException {
      const hint =
          "That isn't a Hypatia pairing code. Scan the one under Remote "
          'access on your computer.';
      if (_scanHint != hint) setState(() => _scanHint = hint);
      return;
    }
    setState(() => _step = _Step.choose);
    _pair(payload);
  }

  Future<void> _checkTyped() async {
    final String origin;
    final String code;
    try {
      origin = parseDesktopAddress(_address.text);
      code = normalizePairingCode(_code.text);
    } on FormatException catch (e) {
      setState(() => _error = e.message);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final fingerprint = await ref.read(certificateFingerprintProvider)(
        origin,
      );
      if (!mounted) return;
      setState(() {
        _origin = origin;
        _typedCode = code;
        _fingerprint = fingerprint;
        _step = _Step.confirm;
      });
    } catch (_) {
      if (!mounted) return;
      setState(
        () => _error =
            "Couldn't reach Hypatia at $origin. Check the address, and that "
            'Remote access is on there.',
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _fingerprintDiffers() => setState(() {
    _step = _Step.enter;
    _error =
        "This phone didn't pair: something other than your computer answered "
        'at that address. Check the address, or scan the QR code instead.';
  });

  Future<void> _pair(PairingPayload payload) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      // On success the gate swaps this screen for the app.
      await ref
          .read(connectionProvider.notifier)
          .pair(payload, deviceName: _deviceName);
    } on PairingException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        if (_step == _Step.confirm) _step = _Step.enter;
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return switch (_step) {
      _Step.scan => _scanner(context),
      _Step.choose => _choose(context),
      _Step.enter => _enter(context),
      _Step.confirm => _confirm(context),
    };
  }

  Widget _scanner(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const BackButtonIcon(),
          tooltip: MaterialLocalizations.of(context).backButtonTooltip,
          onPressed: _back,
        ),
        title: const Text('Scan the pairing code'),
      ),
      body: Column(
        children: [
          Expanded(child: ref.watch(qrScannerProvider)(context, _onScanned)),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                _scanHint ??
                    'On your computer, open Remote access and choose Pair a '
                        'device, then point the camera at the QR code.',
                style: theme.textTheme.bodyMedium,
                textAlign: TextAlign.center,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _nameField() => TextField(
    controller: _name,
    enabled: !_busy,
    textCapitalization: TextCapitalization.words,
    decoration: const InputDecoration(
      labelText: "This device's name",
      helperText: 'Shown on your computer under Paired devices.',
    ),
  );

  Widget _errorText(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: Text(
        _error!,
        style: theme.textTheme.bodyMedium?.copyWith(
          color: theme.colorScheme.error,
        ),
        textAlign: TextAlign.center,
      ),
    );
  }

  Widget _choose(BuildContext context) {
    return GateScreen(
      icon: widget.again ? Icons.link_off : Icons.phonelink_outlined,
      title: widget.again
          ? 'This phone needs pairing again'
          : 'Connect to Hypatia on your computer',
      body: widget.again
          ? 'Your computer no longer accepts this phone. It may have been '
                'removed under Remote access there. To pair again, open '
                'Remote access on your computer and choose Pair a device.'
          : 'Your wiki, chat and study material live on your computer. On '
                'it, open Hypatia, then Remote access. Turn on "Let phones '
                'and tablets connect" and choose Pair a device.',
      children: [
        _nameField(),
        const SizedBox(height: 24),
        if (_busy)
          const Center(child: CircularProgressIndicator())
        else
          Wrap(
            spacing: 12,
            runSpacing: 8,
            alignment: WrapAlignment.center,
            children: [
              if (_canScan)
                FilledButton.icon(
                  onPressed: () => setState(() {
                    _error = null;
                    _step = _Step.scan;
                  }),
                  icon: const Icon(Icons.qr_code_scanner),
                  label: const Text('Scan QR code'),
                ),
              OutlinedButton(
                onPressed: () => setState(() {
                  _error = null;
                  _step = _Step.enter;
                }),
                child: const Text('Enter the code instead'),
              ),
              if (widget.again)
                TextButton(
                  onPressed: () =>
                      ref.read(connectionProvider.notifier).forget(),
                  child: const Text('Forget this computer'),
                ),
            ],
          ),
        if (_error != null) _errorText(context),
      ],
    );
  }

  Widget _enter(BuildContext context) {
    return GateScreen(
      icon: Icons.keyboard_outlined,
      title: 'Enter the pairing code',
      body:
          'Your computer shows its addresses and a code under Remote access, '
          'after Pair a device.',
      onBack: _busy ? null : _back,
      children: [
        TextField(
          controller: _address,
          enabled: !_busy,
          keyboardType: TextInputType.url,
          autocorrect: false,
          textInputAction: TextInputAction.next,
          decoration: const InputDecoration(
            labelText: 'Address',
            hintText: '192.168.1.20:8765',
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _code,
          enabled: !_busy,
          autocorrect: false,
          textCapitalization: TextCapitalization.characters,
          textInputAction: TextInputAction.next,
          inputFormatters: [LengthLimitingTextInputFormatter(12)],
          decoration: const InputDecoration(
            labelText: 'Code',
            hintText: 'K7MQ-2XRP',
          ),
        ),
        const SizedBox(height: 12),
        _nameField(),
        const SizedBox(height: 24),
        Center(
          child: _busy
              ? const CircularProgressIndicator()
              : FilledButton(
                  onPressed: _checkTyped,
                  child: const Text('Continue'),
                ),
        ),
        if (_error != null) _errorText(context),
      ],
    );
  }

  Widget _confirm(BuildContext context) {
    final theme = Theme.of(context);
    return GateScreen(
      icon: Icons.verified_user_outlined,
      title: 'Check the fingerprint',
      body:
          'Under the pairing code, your computer shows a fingerprint. Pair '
          'only if it is the same as this one:',
      onBack: _busy ? null : _back,
      children: [
        SelectableText(
          shortFingerprint(_fingerprint!),
          style: theme.textTheme.headlineSmall?.copyWith(
            fontFamily: 'monospace',
            letterSpacing: 1,
          ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 24),
        if (_busy)
          const Center(child: CircularProgressIndicator())
        else
          Wrap(
            spacing: 12,
            runSpacing: 8,
            alignment: WrapAlignment.center,
            children: [
              FilledButton(
                onPressed: () => _pair(
                  PairingPayload(
                    urls: [_origin!],
                    code: _typedCode!,
                    certSha256: _fingerprint!,
                  ),
                ),
                child: const Text('It matches: pair'),
              ),
              OutlinedButton(
                onPressed: _fingerprintDiffers,
                child: const Text("It's different"),
              ),
            ],
          ),
      ],
    );
  }
}

class _CameraScanner extends StatefulWidget {
  const _CameraScanner({required this.onText});

  final ValueChanged<String> onText;

  @override
  State<_CameraScanner> createState() => _CameraScannerState();
}

class _CameraScannerState extends State<_CameraScanner> {
  final _controller = MobileScannerController(
    formats: const [BarcodeFormat.qrCode],
  );

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MobileScanner(
      controller: _controller,
      onDetect: (capture) {
        for (final barcode in capture.barcodes) {
          if (barcode.rawValue case final text?) widget.onText(text);
        }
      },
      errorBuilder: (context, error) {
        final message = switch (error.errorCode) {
          MobileScannerErrorCode.permissionDenied =>
            "Hypatia can't use the camera. Allow camera access for Hypatia "
                'in Settings, or go back and enter the code instead.',
          MobileScannerErrorCode.unsupported =>
            'This device has no camera Hypatia can use. Go back and enter '
                'the code instead.',
          _ =>
            "The camera didn't start. Go back and try again, or enter the "
                'code instead.',
        };
        return Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(message, textAlign: TextAlign.center),
          ),
        );
      },
    );
  }
}
