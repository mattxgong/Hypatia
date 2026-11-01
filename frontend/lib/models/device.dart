/// A phone or tablet paired for remote access.
class Device {
  const Device({
    required this.id,
    required this.name,
    required this.createdAt,
    this.lastSeenAt,
    this.lastSeenIp,
  });

  factory Device.fromJson(Map<String, dynamic> json) => Device(
    id: json['id'] as String,
    name: json['name'] as String,
    createdAt: DateTime.parse(json['created_at'] as String).toLocal(),
    lastSeenAt: switch (json['last_seen_at']) {
      final String at => DateTime.parse(at).toLocal(),
      _ => null,
    },
    lastSeenIp: json['last_seen_ip'] as String?,
  );

  final String id;
  final String name;
  final DateTime createdAt;
  final DateTime? lastSeenAt;
  final String? lastSeenIp;
}

/// A single-use pairing code and, with remote access on, what the QR carries.
class PairingCode {
  const PairingCode({
    required this.code,
    required this.expiresAt,
    this.urls = const [],
    this.certSha256,
  });

  factory PairingCode.fromJson(Map<String, dynamic> json) => PairingCode(
    code: json['code'] as String,
    expiresAt: DateTime.parse(json['expires_at'] as String).toLocal(),
    urls: (json['urls'] as List<dynamic>? ?? const []).cast<String>(),
    certSha256: json['cert_sha256'] as String?,
  );

  final String code;
  final DateTime expiresAt;
  final List<String> urls;
  final String? certSha256;

  /// The pairing QR's contents: where to connect, the code, and the
  /// certificate fingerprint the phone pins.
  Map<String, dynamic> get qrPayload => {
    'urls': urls,
    'code': code,
    'cert_sha256': certSha256,
  };
}

/// Whether phones can reach this computer, and how.
class RemoteAccessStatus {
  const RemoteAccessStatus({
    required this.enabled,
    this.port,
    this.urls = const [],
    this.certSha256,
  });

  factory RemoteAccessStatus.fromJson(Map<String, dynamic> json) =>
      RemoteAccessStatus(
        enabled: json['enabled'] as bool,
        port: json['port'] as int?,
        urls: (json['urls'] as List<dynamic>).cast<String>(),
        certSha256: json['cert_sha256'] as String?,
      );

  final bool enabled;
  final int? port;
  final List<String> urls;
  final String? certSha256;
}
