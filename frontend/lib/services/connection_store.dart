import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/paired_desktop.dart';

/// Where the pairing (addresses, device token, pinned certificate) is kept.
abstract class ConnectionStore {
  Future<PairedDesktop?> load();
  Future<void> save(PairedDesktop desktop);
  Future<void> clear();
}

/// The Android Keystore or iOS Keychain. Keychain entries survive an
/// uninstall, so a stored token is checked against the desktop before use.
class SecureConnectionStore implements ConnectionStore {
  static const _key = 'hypatia_paired_desktop';
  final _storage = const FlutterSecureStorage();

  @override
  Future<PairedDesktop?> load() async {
    final raw = await _storage.read(key: _key);
    if (raw == null) return null;
    try {
      return PairedDesktop.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } catch (_) {
      // From an older or damaged entry: pairing again replaces it.
      return null;
    }
  }

  @override
  Future<void> save(PairedDesktop desktop) =>
      _storage.write(key: _key, value: jsonEncode(desktop.toJson()));

  @override
  Future<void> clear() => _storage.delete(key: _key);
}

final connectionStoreProvider = Provider<ConnectionStore>(
  (ref) => SecureConnectionStore(),
);

/// Whether DER-encoded certificate bytes are the pinned certificate.
bool certificateMatches(List<int> der, String sha256Hex) =>
    sha256.convert(der).toString() == sha256Hex.toLowerCase();

/// Trusts the desktop's self-signed certificate, and only that one: the
/// certificate whose SHA-256 the pairing QR carried. Pinning compares the
/// certificate, not the host name, so one certificate serves the LAN address
/// and the Tailscale one. Certificates that pass normal validation never
/// reach the callback.
///
/// Installed process-wide, so every `HttpClient` gets it: Dio, the chat
/// WebSocket, and the image and PDF loaders.
class PinnedCertificateOverrides extends HttpOverrides {
  PinnedCertificateOverrides(this.certSha256);

  final String certSha256;

  @override
  HttpClient createHttpClient(SecurityContext? context) =>
      super.createHttpClient(context)
        ..badCertificateCallback = (cert, host, port) =>
            certificateMatches(cert.der, certSha256);
}

/// Pins [certSha256] for every connection from now on, or with null, trusts
/// only normally valid certificates again.
void installCertificatePin(String? certSha256) {
  HttpOverrides.global = certSha256 == null
      ? null
      : PinnedCertificateOverrides(certSha256);
}

/// How the connection layer installs the pin; tests replace it, since the
/// test binding owns `HttpOverrides.global`.
final certificatePinProvider = Provider<void Function(String?)>(
  (ref) => installCertificatePin,
);
