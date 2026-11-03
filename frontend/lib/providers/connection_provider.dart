import 'dart:async';
import 'dart:math' as math;

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/paired_desktop.dart';
import '../services/api_client.dart';
import '../services/connection_store.dart';

/// Whether this app reaches its backend over the network, paired with a
/// desktop (phones and tablets), rather than launching one itself. Set in
/// `main()`; false in tests unless overridden.
final remoteClientProvider = Provider<bool>((ref) => false);

enum ConnectionStatus {
  /// Reading the stored pairing.
  checking,

  /// Not paired with any computer.
  unpaired,

  /// Trying the desktop's addresses.
  connecting,

  connected,

  /// None of the desktop's addresses answered. Retried with backoff.
  desktopUnreachable,

  /// The desktop rejected this phone's token: revoked, or a different
  /// computer now answers at that address. Pairing again is the way out.
  unauthorized,
}

class RemoteConnection {
  const RemoteConnection(
    this.status, {
    this.desktop,
    this.url,
    this.hasConnected = false,
  });

  final ConnectionStatus status;
  final PairedDesktop? desktop;

  /// The address in use, while connected.
  final String? url;

  /// Whether this run of the app has reached the desktop yet. After it has,
  /// the app stays on screen through a dropped connection.
  final bool hasConnected;

  RemoteConnection copyWith({
    ConnectionStatus? status,
    PairedDesktop? desktop,
    String? url,
  }) => RemoteConnection(
    status ?? this.status,
    desktop: desktop ?? this.desktop,
    url: url ?? this.url,
    hasConnected: hasConnected || status == ConnectionStatus.connected,
  );
}

/// Why pairing failed, in words for the user.
class PairingException implements Exception {
  const PairingException(this.message);
  final String message;

  @override
  String toString() => message;
}

/// For pairing and connection checks, before an [ApiClient] exists.
final connectionDioProvider = Provider<Dio>(
  (ref) => Dio(
    BaseOptions(
      connectTimeout: const Duration(seconds: 4),
      receiveTimeout: const Duration(seconds: 8),
    ),
  ),
);

/// Minimum and maximum wait between retries while the desktop is unreachable.
const connectionRetryMin = Duration(seconds: 5);
const connectionRetryMax = Duration(seconds: 60);

enum _Check { ok, unauthorized, unreachable }

/// Owns the phone's link to the paired desktop: which address to use, the
/// device token, the pinned certificate, and the status the UI shows. It sets
/// [backendBaseUrlProvider] and [backendApiTokenProvider], which the rest of
/// the app already follows (the desktop launcher sets them the same way).
class ConnectionNotifier extends Notifier<RemoteConnection> {
  Timer? _retry;
  int _failures = 0;
  Future<void>? _probing;

  ConnectionStore get _store => ref.read(connectionStoreProvider);
  Dio get _dio => ref.read(connectionDioProvider);

  @override
  RemoteConnection build() {
    ref.onDispose(() => _retry?.cancel());
    Future.microtask(_load);
    return const RemoteConnection(ConnectionStatus.checking);
  }

  Future<void> _load() async {
    final desktop = await _store.load();
    if (desktop == null) {
      state = const RemoteConnection(ConnectionStatus.unpaired);
      return;
    }
    ref.read(certificatePinProvider)(desktop.certSha256);
    state = RemoteConnection(ConnectionStatus.connecting, desktop: desktop);
    await probe();
  }

  /// Tries the desktop's addresses in order and connects to the first that
  /// answers. Concurrent calls share one attempt.
  Future<void> probe() => _probing ??= _probe().whenComplete(() {
    _probing = null;
  });

  Future<void> _probe() async {
    final desktop = state.desktop;
    if (desktop == null) return;
    _retry?.cancel();
    // While connected the app keeps working on the current address; only a
    // first connection shows "connecting".
    if (state.status != ConnectionStatus.connected) {
      state = state.copyWith(status: ConnectionStatus.connecting);
    }
    for (final url in desktop.urlsToTry) {
      switch (await _check(url, desktop.token)) {
        case _Check.ok:
          await _connected(desktop, url);
          return;
        case _Check.unauthorized:
          state = state.copyWith(status: ConnectionStatus.unauthorized);
          return;
        case _Check.unreachable:
          continue;
      }
    }
    state = state.copyWith(status: ConnectionStatus.desktopUnreachable);
    _scheduleRetry();
  }

  /// An authenticated request the app makes anyway, so a pass means the
  /// address, the certificate and the token all work.
  Future<_Check> _check(String url, String token) async {
    try {
      await _dio.get<dynamic>(
        '$url/api/classes',
        options: Options(headers: {'Authorization': 'Bearer $token'}),
      );
      return _Check.ok;
    } on DioException catch (e) {
      return e.response?.statusCode == 401
          ? _Check.unauthorized
          : _Check.unreachable;
    }
  }

  void _scheduleRetry() {
    _failures++;
    final seconds = math.min(
      connectionRetryMin.inSeconds * (1 << math.min(_failures - 1, 4)),
      connectionRetryMax.inSeconds,
    );
    _retry = Timer(Duration(seconds: seconds), probe);
  }

  Future<void> _connected(PairedDesktop desktop, String url) async {
    _failures = 0;
    if (desktop.lastUrl != url) {
      desktop = desktop.withLastUrl(url);
      await _store.save(desktop);
    }
    // Token first: both rebuild the ApiClient, and it must never pair the new
    // address with a stale token.
    ref.read(backendApiTokenProvider.notifier).state = desktop.token;
    ref.read(backendBaseUrlProvider.notifier).state = url;
    state = state.copyWith(
      status: ConnectionStatus.connected,
      desktop: desktop,
      url: url,
    );
  }

  /// Redeems a pairing code at the first of the desktop's addresses that
  /// answers, then stores the pairing and connects. Throws
  /// [PairingException] with a message for the user.
  Future<void> pair(
    PairingPayload payload, {
    required String deviceName,
  }) async {
    final previous = state.desktop;
    ref.read(certificatePinProvider)(payload.certSha256);
    for (final url in payload.urls) {
      final Response<Map<String, dynamic>> response;
      try {
        response = await _dio.post<Map<String, dynamic>>(
          '$url/api/devices/pair',
          data: {'code': payload.code, 'device_name': deviceName},
        );
      } on DioException catch (e) {
        if (e.response == null) continue; // Not reachable here; try the next.
        ref.read(certificatePinProvider)(previous?.certSha256);
        final data = e.response!.data;
        throw PairingException(
          data is Map && data['detail'] is String
              ? data['detail'] as String
              : 'Pairing failed (${e.response!.statusCode}).',
        );
      }
      final body = response.data!;
      final device = body['device'] as Map<String, dynamic>;
      // The desktop lists all its addresses (LAN, then Tailscale); keep any
      // typed one it doesn't know, such as a host name.
      final known = (body['urls'] as List<dynamic>? ?? const []).cast<String>();
      final desktop = PairedDesktop(
        urls: {...known, ...payload.urls}.toList(),
        token: body['token'] as String,
        certSha256: payload.certSha256,
        deviceId: device['id'] as String,
        deviceName: device['name'] as String,
        lastUrl: url,
      );
      await _store.save(desktop);
      _retry?.cancel();
      state = RemoteConnection(ConnectionStatus.connecting, desktop: desktop);
      await _connected(desktop, url);
      return;
    }
    ref.read(certificatePinProvider)(previous?.certSha256);
    throw const PairingException(
      "Couldn't reach your computer at any of its addresses. Check that "
      'Hypatia is open there with Remote access on, and that this phone is '
      'on the same network or Tailscale.',
    );
  }

  /// Unpairs: forgets the token and the pinned certificate.
  Future<void> forget() async {
    _retry?.cancel();
    await _store.clear();
    ref.read(certificatePinProvider)(null);
    ref.read(backendApiTokenProvider.notifier).state = null;
    state = const RemoteConnection(ConnectionStatus.unpaired);
  }

  /// A request got 401: the token no longer works.
  void reportUnauthorized() {
    if (state.desktop == null) return;
    _retry?.cancel();
    state = state.copyWith(status: ConnectionStatus.unauthorized);
  }

  /// A request couldn't reach the desktop: the network may have changed (Wi-Fi
  /// dropped, so Tailscale is the way now), so look for a working address.
  void reportUnreachable() {
    if (state.status == ConnectionStatus.connected) unawaited(probe());
  }

  /// The app came back to the foreground: the network may have changed while
  /// it was away.
  Future<void> resume() async {
    if (state.desktop == null ||
        state.status == ConnectionStatus.unauthorized) {
      return;
    }
    _failures = 0;
    await probe();
  }
}

final connectionProvider =
    NotifierProvider<ConnectionNotifier, RemoteConnection>(
      ConnectionNotifier.new,
    );
