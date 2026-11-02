import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/models/paired_desktop.dart';
import 'package:frontend/providers/connection_provider.dart';
import 'package:frontend/services/api_client.dart';
import 'package:frontend/services/connection_store.dart';
import 'package:frontend/widgets/remote/connection_gate.dart';
import 'package:frontend/widgets/remote/pairing_screen.dart';

const _lan = 'https://192.168.1.20:8765';
const _tailscale = 'https://desk.tail1.ts.net:8765';
const _pin = 'ab12cd34ef567890ffff';
final _qr = jsonEncode({
  'urls': [_lan, _tailscale],
  'code': 'K7MQ2XRP',
  'cert_sha256': _pin,
});

/// The desktop's addresses: which answer, and how.
class _FakeDesktop implements HttpClientAdapter {
  final reachable = <String>{_lan, _tailscale};
  String validToken = 'good-token';
  String validCode = 'K7MQ2XRP';
  final requests = <String>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final uri = options.uri;
    final origin = '${uri.scheme}://${uri.host}:${uri.port}';
    requests.add('${options.method} $origin${uri.path}');
    if (!reachable.contains(origin)) {
      throw DioException(
        requestOptions: options,
        type: DioExceptionType.connectionError,
      );
    }
    if (uri.path == '/api/devices/pair') {
      final body = options.data as Map<String, dynamic>;
      if (body['code'] != validCode) {
        return _json(400, {
          'detail': 'That pairing code is wrong or has expired.',
          'code': 'PAIRING_CODE_INVALID',
        });
      }
      return _json(201, {
        'device': {
          'id': 'd1',
          'name': body['device_name'],
          'created_at': '2026-11-01T00:00:00Z',
          'last_seen_at': null,
          'last_seen_ip': null,
        },
        'token': validToken,
        'urls': [_lan, _tailscale],
      });
    }
    if (options.headers['Authorization'] != 'Bearer $validToken') {
      return _json(401, {'detail': 'Invalid token', 'code': 'AUTH_INVALID'});
    }
    return _json(200, <dynamic>[]);
  }

  ResponseBody _json(int status, Object body) => ResponseBody.fromString(
    jsonEncode(body),
    status,
    headers: {
      Headers.contentTypeHeader: [Headers.jsonContentType],
    },
  );

  @override
  void close({bool force = false}) {}
}

class _MemoryStore implements ConnectionStore {
  PairedDesktop? desktop;

  @override
  Future<PairedDesktop?> load() async => desktop;

  @override
  Future<void> save(PairedDesktop desktop) async => this.desktop = desktop;

  @override
  Future<void> clear() async => desktop = null;
}

PairedDesktop _paired({String token = 'good-token', String? lastUrl}) =>
    PairedDesktop(
      urls: const [_lan, _tailscale],
      token: token,
      certSha256: _pin,
      deviceId: 'd1',
      deviceName: 'Pixel 9',
      lastUrl: lastUrl,
    );

void main() {
  late _FakeDesktop desktop;
  late _MemoryStore store;
  late List<String?> pins;
  // What answers a fingerprint check for a typed address.
  late String presentedCert;

  ProviderContainer makeContainer() {
    final dio = Dio()..httpClientAdapter = desktop;
    final container = ProviderContainer(
      overrides: [
        remoteClientProvider.overrideWithValue(true),
        connectionStoreProvider.overrideWithValue(store),
        connectionDioProvider.overrideWithValue(dio),
        certificatePinProvider.overrideWithValue(pins.add),
        certificateFingerprintProvider.overrideWithValue((origin) async {
          if (!desktop.reachable.contains(origin)) {
            throw const SocketException('unreachable');
          }
          return presentedCert;
        }),
        // A button per code the "camera" could see.
        qrScannerProvider.overrideWithValue(
          (context, onText) => Column(
            children: [
              TextButton(
                onPressed: () => onText('https://example.com'),
                child: const Text('see a website QR'),
              ),
              TextButton(
                onPressed: () => onText(_qr),
                child: const Text('see the pairing QR'),
              ),
            ],
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    return container;
  }

  /// Lets the stored pairing load and the first check finish.
  Future<RemoteConnection> settle(ProviderContainer container) async {
    container.read(connectionProvider);
    for (var i = 0; i < 10; i++) {
      await Future<void>.delayed(Duration.zero);
    }
    return container.read(connectionProvider);
  }

  setUp(() {
    desktop = _FakeDesktop();
    store = _MemoryStore();
    pins = [];
    presentedCert = _pin;
  });

  group('models', () {
    test('the pairing QR parses, and anything else is refused', () {
      final payload = PairingPayload.parse(
        jsonEncode({
          'urls': [_lan, _tailscale],
          'code': 'K7MQ2XRP',
          'cert_sha256': _pin,
        }),
      );
      expect(payload.urls, [_lan, _tailscale]);
      expect(payload.code, 'K7MQ2XRP');

      for (final bad in [
        'https://example.com',
        '{"urls": [], "code": "x", "cert_sha256": "y"}',
        '{"code": "x"}',
      ]) {
        expect(() => PairingPayload.parse(bad), throwsFormatException);
      }
    });

    test('the address that worked last is tried first', () {
      expect(_paired().urlsToTry, [_lan, _tailscale]);
      expect(_paired(lastUrl: _tailscale).urlsToTry, [_tailscale, _lan]);
      expect(
        PairedDesktop.fromJson(_paired(lastUrl: _lan).toJson()).urlsToTry,
        [_lan, _tailscale],
      );
    });

    test('typed addresses and codes are read leniently', () {
      expect(parseDesktopAddress(' 192.168.1.20 '), _lan);
      expect(parseDesktopAddress('http://192.168.1.20:8765/'), _lan);
      expect(parseDesktopAddress('desk.tail1.ts.net:9000'), endsWith(':9000'));
      for (final bad in ['', '   ', 'https://']) {
        expect(() => parseDesktopAddress(bad), throwsFormatException);
      }
      expect(normalizePairingCode(' k7mq-2xrp'), 'K7MQ2XRP');
      expect(() => normalizePairingCode('K7MQ'), throwsFormatException);
      expect(shortFingerprint(_pin), 'AB12 CD34 EF56 7890');
    });

    test('a certificate matches only its own fingerprint', () {
      final der = utf8.encode('certificate bytes');
      final pin = sha256.convert(der).toString();
      expect(certificateMatches(der, pin), isTrue);
      expect(certificateMatches(der, pin.toUpperCase()), isTrue);
      expect(certificateMatches(utf8.encode('another'), pin), isFalse);
    });
  });

  group('connecting', () {
    test('with nothing stored, the phone is unpaired', () async {
      final state = await settle(makeContainer());
      expect(state.status, ConnectionStatus.unpaired);
      expect(pins, isEmpty);
    });

    test('falls back to Tailscale when the LAN address is out of reach, and '
        'remembers it', () async {
      store.desktop = _paired();
      desktop.reachable.remove(_lan);
      final container = makeContainer();

      final state = await settle(container);
      expect(state.status, ConnectionStatus.connected);
      expect(state.url, _tailscale);
      expect(pins, [_pin]);
      expect(store.desktop!.lastUrl, _tailscale);
      expect(container.read(backendBaseUrlProvider), _tailscale);
      expect(container.read(backendApiTokenProvider), 'good-token');
    });

    test('a revoked token stops at "pair again" without retrying', () async {
      store.desktop = _paired(token: 'revoked');
      final state = await settle(makeContainer());
      expect(state.status, ConnectionStatus.unauthorized);
      expect(desktop.requests, ['GET $_lan/api/classes']);
    });

    test('an unreachable desktop is reported, and found again later', () async {
      store.desktop = _paired();
      desktop.reachable.clear();
      final container = makeContainer();
      expect(
        (await settle(container)).status,
        ConnectionStatus.desktopUnreachable,
      );

      desktop.reachable.add(_lan);
      await container.read(connectionProvider.notifier).probe();
      expect(
        container.read(connectionProvider).status,
        ConnectionStatus.connected,
      );
    });

    test('losing the LAN mid-session switches to Tailscale', () async {
      store.desktop = _paired();
      final container = makeContainer();
      expect((await settle(container)).url, _lan);

      desktop.reachable.remove(_lan);
      container.read(connectionProvider.notifier).reportUnreachable();
      await settle(container);
      final state = container.read(connectionProvider);
      expect(state.status, ConnectionStatus.connected);
      expect(state.url, _tailscale);
      expect(container.read(backendBaseUrlProvider), _tailscale);
    });
  });

  group('pairing', () {
    PairingPayload payload({String code = 'K7MQ2XRP'}) => PairingPayload(
      urls: const [_lan, _tailscale],
      code: code,
      certSha256: _pin,
    );

    test('redeems the code, stores the token and connects', () async {
      desktop.reachable.remove(_lan);
      final container = makeContainer();
      await settle(container);

      await container
          .read(connectionProvider.notifier)
          .pair(payload(), deviceName: 'Pixel 9');
      final state = container.read(connectionProvider);
      expect(state.status, ConnectionStatus.connected);
      expect(state.url, _tailscale);
      expect(store.desktop!.token, 'good-token');
      expect(store.desktop!.deviceName, 'Pixel 9');
      expect(pins.last, _pin);
    });

    test('a code typed for one address learns the others', () async {
      final container = makeContainer();
      await settle(container);

      await container
          .read(connectionProvider.notifier)
          .pair(
            const PairingPayload(
              urls: [_tailscale],
              code: 'K7MQ2XRP',
              certSha256: _pin,
            ),
            deviceName: 'Pixel 9',
          );
      expect(store.desktop!.urls, [_lan, _tailscale]);
      expect(store.desktop!.lastUrl, _tailscale);
    });

    test('a wrong code says so and leaves the phone unpaired', () async {
      final container = makeContainer();
      await settle(container);

      await expectLater(
        container
            .read(connectionProvider.notifier)
            .pair(payload(code: 'WRONG123'), deviceName: 'Pixel 9'),
        throwsA(
          isA<PairingException>().having(
            (e) => e.message,
            'message',
            contains('wrong or has expired'),
          ),
        ),
      );
      expect(store.desktop, isNull);
      expect(pins.last, isNull);
      // The code is refused at the first address; it isn't tried again.
      expect(desktop.requests, ['POST $_lan/api/devices/pair']);
    });

    test('no address answering is explained', () async {
      desktop.reachable.clear();
      final container = makeContainer();
      await settle(container);

      await expectLater(
        container
            .read(connectionProvider.notifier)
            .pair(payload(), deviceName: 'Pixel 9'),
        throwsA(isA<PairingException>()),
      );
      expect(desktop.requests, hasLength(2));
    });

    test('forgetting unpairs and drops the pin', () async {
      store.desktop = _paired();
      final container = makeContainer();
      await settle(container);

      await container.read(connectionProvider.notifier).forget();
      expect(
        container.read(connectionProvider).status,
        ConnectionStatus.unpaired,
      );
      expect(store.desktop, isNull);
      expect(pins.last, isNull);
    });
  });

  test('a 401 from any request asks for pairing again', () async {
    store.desktop = _paired();
    final container = makeContainer();
    await settle(container);

    desktop.validToken = 'rotated';
    final api = container.read(apiClientProvider);
    // The real client talks to the network; give it the fake desktop too.
    await expectLater(
      () => _withAdapter(api, desktop).listClasses(),
      throwsA(isA<ApiException>()),
    );
    expect(
      container.read(connectionProvider).status,
      ConnectionStatus.unauthorized,
    );
  });

  group('gate', () {
    // In fake time: the stored pairing loads and the check runs as frames
    // pass.
    Future<void> flush(WidgetTester tester) async {
      for (var i = 0; i < 20; i++) {
        await tester.pump(const Duration(milliseconds: 10));
      }
    }

    Future<ProviderContainer> pumpGate(WidgetTester tester) async {
      final container = makeContainer();
      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: const MaterialApp(home: ConnectionGate(child: _App())),
        ),
      );
      await flush(tester);
      return container;
    }

    testWidgets('an unpaired phone explains how to pair', (tester) async {
      await pumpGate(tester);
      expect(find.text('Connect to Hypatia on your computer'), findsOneWidget);
      expect(find.byType(_App), findsNothing);
    });

    testWidgets('a dropped connection shows a banner over the same app', (
      tester,
    ) async {
      store.desktop = _paired();
      final container = await pumpGate(tester);
      expect(find.byType(_App), findsOneWidget);
      final app = tester.state(find.byType(_App));

      desktop.reachable.clear();
      container.read(connectionProvider.notifier).reportUnreachable();
      await flush(tester);
      expect(
        container.read(connectionProvider).status,
        ConnectionStatus.desktopUnreachable,
      );
      expect(find.text("Can't reach your computer. Retrying."), findsOneWidget);
      expect(tester.state(find.byType(_App)), same(app));
      // Stops the retry timer before the test ends.
      await container.read(connectionProvider.notifier).forget();
    });

    testWidgets('a revoked phone is asked to pair again, and can', (
      tester,
    ) async {
      store.desktop = _paired(token: 'revoked');
      await pumpGate(tester);
      expect(find.text('This phone needs pairing again'), findsOneWidget);

      await tester.tap(find.text('Scan QR code'));
      await flush(tester);
      await tester.tap(find.text('see the pairing QR'));
      await flush(tester);
      expect(find.byType(_App), findsOneWidget);
      expect(store.desktop!.token, 'good-token');
    });

    group('pairing', () {
      testWidgets('scanning the QR pairs, and other codes are explained', (
        tester,
      ) async {
        final container = await pumpGate(tester);
        await tester.enterText(
          find.widgetWithText(TextField, "This device's name"),
          'Pixel 9',
        );
        await tester.tap(find.text('Scan QR code'));
        await flush(tester);

        await tester.tap(find.text('see a website QR'));
        await flush(tester);
        expect(
          find.textContaining("isn't a Hypatia pairing code"),
          findsOneWidget,
        );

        await tester.tap(find.text('see the pairing QR'));
        await flush(tester);
        expect(find.byType(_App), findsOneWidget);
        expect(
          container.read(connectionProvider).status,
          ConnectionStatus.connected,
        );
        expect(store.desktop!.deviceName, 'Pixel 9');
      });

      Future<void> tapText(WidgetTester tester, String text) async {
        await tester.ensureVisible(find.text(text));
        await tester.tap(find.text(text));
        await flush(tester);
      }

      Future<void> typeCode(
        WidgetTester tester, {
        String address = '192.168.1.20',
        String code = 'k7mq-2xrp',
      }) async {
        await tapText(tester, 'Enter the code instead');
        await tester.enterText(
          find.widgetWithText(TextField, 'Address'),
          address,
        );
        await tester.enterText(find.widgetWithText(TextField, 'Code'), code);
        await tapText(tester, 'Continue');
      }

      testWidgets('a typed code pairs once the fingerprint is confirmed', (
        tester,
      ) async {
        await pumpGate(tester);
        await typeCode(tester);

        expect(find.text('AB12 CD34 EF56 7890'), findsOneWidget);
        // Nothing is sent before the user checks the fingerprint.
        expect(desktop.requests, isEmpty);

        await tester.tap(find.text('It matches: pair'));
        await flush(tester);
        expect(find.byType(_App), findsOneWidget);
        expect(desktop.requests, ['POST $_lan/api/devices/pair']);
        expect(store.desktop!.certSha256, _pin);
        expect(store.desktop!.urls, [_lan, _tailscale]);
      });

      testWidgets('a different fingerprint stops pairing', (tester) async {
        presentedCert = 'ffff0000ffff0000';
        await pumpGate(tester);
        await typeCode(tester);

        expect(find.text('FFFF 0000 FFFF 0000'), findsOneWidget);
        await tester.tap(find.text("It's different"));
        await flush(tester);
        expect(find.textContaining("didn't pair"), findsOneWidget);
        expect(desktop.requests, isEmpty);
        expect(store.desktop, isNull);
      });

      testWidgets('typing mistakes and a wrong code are explained', (
        tester,
      ) async {
        await pumpGate(tester);
        await typeCode(tester, code: 'K7M');
        expect(find.text('The code has 8 letters and digits.'), findsOneWidget);

        await tester.enterText(
          find.widgetWithText(TextField, 'Address'),
          '10.0.0.9',
        );
        await tester.enterText(
          find.widgetWithText(TextField, 'Code'),
          'K7MQ2XRP',
        );
        await tester.tap(find.text('Continue'));
        await flush(tester);
        expect(
          find.textContaining("Couldn't reach Hypatia at"),
          findsOneWidget,
        );

        await tester.enterText(
          find.widgetWithText(TextField, 'Address'),
          '192.168.1.20',
        );
        await tester.enterText(
          find.widgetWithText(TextField, 'Code'),
          'WRONG234',
        );
        await tester.tap(find.text('Continue'));
        await flush(tester);
        await tester.tap(find.text('It matches: pair'));
        await flush(tester);
        expect(find.textContaining('wrong or has expired'), findsOneWidget);
        expect(find.widgetWithText(TextField, 'Code'), findsOneWidget);
      });

      testWidgets('every step fits a small phone', (tester) async {
        tester.view.physicalSize = const Size(360, 560);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        await pumpGate(tester);
        expect(find.text('Android phone'), findsOneWidget);
        await typeCode(tester);
        await tapText(tester, 'It matches: pair');
        expect(find.byType(_App), findsOneWidget);
        expect(tester.takeException(), isNull);
      });

      testWidgets("Android's Back steps back through the flow", (tester) async {
        await pumpGate(tester);
        await tester.tap(find.text('Enter the code instead'));
        await flush(tester);
        expect(find.text('Enter the pairing code'), findsOneWidget);

        expect(await tester.binding.handlePopRoute(), isTrue);
        await flush(tester);
        expect(
          find.text('Connect to Hypatia on your computer'),
          findsOneWidget,
        );
      });
    });

    testWidgets('the phone can forget its computer from the app', (
      tester,
    ) async {
      store.desktop = _paired();
      await pumpGate(tester);
      await tester.tap(find.text('the app'));
      await flush(tester);
      expect(find.text('Connected at $_lan'), findsOneWidget);

      await tester.tap(find.text('Forget this computer'));
      await flush(tester);
      await tester.tap(find.text('Forget'));
      await flush(tester);
      expect(find.text('Connect to Hypatia on your computer'), findsOneWidget);
      expect(store.desktop, isNull);
    });
  });
}

/// The same client, sending through [adapter].
ApiClient _withAdapter(ApiClient api, HttpClientAdapter adapter) {
  api.debugDio.httpClientAdapter = adapter;
  return api;
}

class _App extends StatefulWidget {
  const _App();

  @override
  State<_App> createState() => _AppState();
}

class _AppState extends State<_App> {
  @override
  Widget build(BuildContext context) => TextButton(
    onPressed: () => showPairedComputerDialog(context),
    child: const Text('the app'),
  );
}
