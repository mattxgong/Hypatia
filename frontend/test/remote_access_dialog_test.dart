import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qr_flutter/qr_flutter.dart';

import 'package:frontend/models/device.dart';
import 'package:frontend/providers/backend_provider.dart';
import 'package:frontend/services/api_client.dart';
import 'package:frontend/services/backend_launcher.dart';
import 'package:frontend/widgets/remote/remote_access_dialog.dart';

class _FakeApi extends ApiClient {
  _FakeApi({required this.status}) : super(baseUrl: 'http://test');

  RemoteAccessStatus status;
  List<Device> devices = [];
  final revoked = <String>[];
  int codesIssued = 0;

  @override
  Future<RemoteAccessStatus> getRemoteAccess() async => status;

  @override
  Future<List<Device>> listDevices() async => devices;

  @override
  Future<void> revokeDevice(String deviceId) async {
    revoked.add(deviceId);
    devices = devices.where((d) => d.id != deviceId).toList();
  }

  @override
  Future<PairingCode> createPairingCode() async {
    codesIssued++;
    return PairingCode(
      code: 'K7MQ2XRP',
      expiresAt: DateTime.now().add(const Duration(minutes: 5)),
      urls: status.urls,
      certSha256: status.certSha256,
    );
  }
}

class _FakeLauncher extends BackendLauncher {
  final changes = <RemoteAccess>[];

  @override
  RemoteAccess get remoteAccess => const RemoteAccess();

  @override
  Future<void> setRemoteAccess(RemoteAccess access) async =>
      changes.add(access);
}

Device _device(String id, String name, {DateTime? seen}) => Device(
  id: id,
  name: name,
  createdAt: DateTime(2026, 10, 30),
  lastSeenAt: seen,
  lastSeenIp: seen == null ? null : '192.168.1.30',
);

const _on = RemoteAccessStatus(
  enabled: true,
  port: 8765,
  urls: ['https://192.168.1.20:8765', 'https://desk.tail1.ts.net:8765'],
  certSha256: 'ab12',
);

void main() {
  late _FakeApi api;
  late _FakeLauncher launcher;

  Future<void> open(
    WidgetTester tester, {
    Size size = const Size(1200, 1400),
  }) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          apiClientProvider.overrideWithValue(api),
          backendLauncherProvider.overrideWithValue(launcher),
        ],
        child: MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => TextButton(
                onPressed: () => showRemoteAccessDialog(context),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
  }

  setUp(() {
    launcher = _FakeLauncher();
  });

  testWidgets('off: no pairing, but paired devices can be revoked', (
    tester,
  ) async {
    api = _FakeApi(status: const RemoteAccessStatus(enabled: false))
      ..devices = [
        _device(
          'd1',
          'Pixel 9',
          seen: DateTime.now().subtract(const Duration(minutes: 5)),
        ),
        _device('d2', 'iPad'),
      ];
    await open(tester);

    expect(
      tester.widget<SwitchListTile>(find.byType(SwitchListTile)).value,
      isFalse,
    );
    expect(find.text('Pair a device'), findsNothing);
    expect(
      find.text('Last seen 5 minutes ago from 192.168.1.30'),
      findsOneWidget,
    );
    expect(find.text('Not connected yet'), findsOneWidget);

    await tester.tap(find.text('Revoke').first);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Revoke'));
    await tester.pumpAndSettle();

    expect(api.revoked, ['d1']);
    expect(find.text('Pixel 9'), findsNothing);
  });

  testWidgets('on: the QR carries the addresses, code and fingerprint', (
    tester,
  ) async {
    api = _FakeApi(status: _on);
    await open(tester);

    expect(find.text('https://192.168.1.20:8765'), findsOneWidget);
    await tester.tap(find.text('Pair a device'));
    await tester.pump();

    expect(find.byType(QrImageView), findsOneWidget);
    expect(find.text('K7MQ-2XRP'), findsOneWidget);
    expect(find.textContaining('Expires in 4:'), findsOneWidget);

    // The phone pairs: the next device check finds it and the code goes away.
    api.devices = [_device('d1', 'Pixel 9')];
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    await tester.pump();
    expect(find.byType(QrImageView), findsNothing);
    expect(find.text('Device paired.'), findsOneWidget);
    expect(find.text('Pixel 9'), findsOneWidget);
  });

  testWidgets('the pairing code and QR fit a phone screen', (tester) async {
    api = _FakeApi(status: _on);
    await open(tester, size: const Size(390, 844));
    await tester.tap(find.text('Pair a device'));
    await tester.pump();
    expect(find.byType(QrImageView), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the toggle restarts the backend with the new setting', (
    tester,
  ) async {
    api = _FakeApi(status: const RemoteAccessStatus(enabled: false));
    await open(tester);

    await tester.tap(find.byType(Switch));
    await tester.pumpAndSettle();
    expect(find.textContaining('private networks only'), findsOneWidget);
    await tester.tap(find.text('Restart backend'));
    await tester.pumpAndSettle();

    expect(launcher.changes.single.enabled, isTrue);
    expect(find.byType(AlertDialog), findsNothing);
  });

  test('last-seen and code formatting', () {
    final now = DateTime(2026, 11, 1, 12);
    expect(describeLastSeen(now, now), 'just now');
    expect(
      describeLastSeen(now.subtract(const Duration(hours: 3)), now),
      '3 hours ago',
    );
    expect(describeLastSeen(DateTime(2026, 10, 2), now), 'on 2026-10-02');
    expect(formatPairingCode('K7MQ2XRP'), 'K7MQ-2XRP');
  });

  test('the QR encodes the addresses, code and fingerprint as JSON', () {
    final code = PairingCode(
      code: 'K7MQ2XRP',
      expiresAt: DateTime(2026),
      urls: _on.urls,
      certSha256: 'ab12',
    );
    expect(jsonDecode(pairingQrData(code)), {
      'urls': _on.urls,
      'code': 'K7MQ2XRP',
      'cert_sha256': 'ab12',
    });
  });
}
