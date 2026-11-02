import 'dart:convert';

/// What the desktop's pairing QR carries: where to connect, the single-use
/// code, and the SHA-256 of the certificate to pin.
class PairingPayload {
  const PairingPayload({
    required this.urls,
    required this.code,
    required this.certSha256,
  });

  /// Reads the QR's JSON; throws [FormatException] for anything else.
  factory PairingPayload.parse(String text) {
    final Object? json;
    try {
      json = jsonDecode(text);
    } on FormatException {
      throw const FormatException('Not a Hypatia pairing code.');
    }
    if (json case {
      'urls': final List<dynamic> urls,
      'code': final String code,
      'cert_sha256': final String cert,
    } when urls.isNotEmpty && urls.every((u) => u is String)) {
      return PairingPayload(
        urls: urls.cast<String>(),
        code: code,
        certSha256: cert,
      );
    }
    throw const FormatException('Not a Hypatia pairing code.');
  }

  final List<String> urls;
  final String code;
  final String certSha256;
}

/// The port the desktop listens on for phones, unless it was changed.
const defaultDesktopPort = 8765;

/// An address typed by hand ("192.168.1.20", "desk.tail1.ts.net:9000",
/// "https://...") as the origin to connect to. The desktop speaks only HTTPS
/// to phones, so any scheme typed becomes https. Throws [FormatException].
String parseDesktopAddress(String input) {
  var text = input.trim();
  if (text.isEmpty) throw const FormatException('Enter the address.');
  if (!text.contains('://')) text = 'https://$text';
  final uri = Uri.tryParse(text);
  if (uri == null || uri.host.isEmpty) {
    throw const FormatException("That doesn't look like an address.");
  }
  return Uri(
    scheme: 'https',
    host: uri.host,
    port: uri.hasPort ? uri.port : defaultDesktopPort,
  ).origin;
}

/// A pairing code as typed ("k7mq-2xrp ") in the desktop's form ("K7MQ2XRP").
/// Throws [FormatException] unless it has the 8 characters codes have.
String normalizePairingCode(String input) {
  final code = input.replaceAll(RegExp(r'[\s-]'), '').toUpperCase();
  if (!RegExp(r'^[A-Z0-9]{8}$').hasMatch(code)) {
    throw const FormatException('The code has 8 letters and digits.');
  }
  return code;
}

/// The start of a certificate's SHA-256 as "AB12 CD34 EF56 7890": what the
/// desktop shows beside the pairing code, for checking a code typed by hand.
String shortFingerprint(String sha256Hex) {
  final hex = sha256Hex.toUpperCase();
  return [
    for (var i = 0; i < 16 && i + 4 <= hex.length; i += 4)
      hex.substring(i, i + 4),
  ].join(' ');
}

/// The computer this phone is paired with, kept in secure storage.
class PairedDesktop {
  const PairedDesktop({
    required this.urls,
    required this.token,
    required this.certSha256,
    required this.deviceId,
    required this.deviceName,
    this.lastUrl,
  });

  factory PairedDesktop.fromJson(Map<String, dynamic> json) => PairedDesktop(
    urls: (json['urls'] as List<dynamic>).cast<String>(),
    token: json['token'] as String,
    certSha256: json['cert_sha256'] as String,
    deviceId: json['device_id'] as String,
    deviceName: json['device_name'] as String,
    lastUrl: json['last_url'] as String?,
  );

  /// The desktop's addresses, LAN first, then Tailscale.
  final List<String> urls;

  /// This phone's device token (the desktop stores only its hash).
  final String token;
  final String certSha256;
  final String deviceId;
  final String deviceName;

  /// The address that answered last, tried first next time.
  final String? lastUrl;

  /// The order to try addresses in: the last one that worked, then the rest.
  List<String> get urlsToTry => [
    if (lastUrl != null && urls.contains(lastUrl)) lastUrl!,
    for (final url in urls)
      if (url != lastUrl) url,
  ];

  PairedDesktop withLastUrl(String url) => PairedDesktop(
    urls: urls,
    token: token,
    certSha256: certSha256,
    deviceId: deviceId,
    deviceName: deviceName,
    lastUrl: url,
  );

  Map<String, dynamic> toJson() => {
    'urls': urls,
    'token': token,
    'cert_sha256': certSha256,
    'device_id': deviceId,
    'device_name': deviceName,
    'last_url': lastUrl,
  };
}
