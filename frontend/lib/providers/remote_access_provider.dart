import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/device.dart';
import '../services/api_client.dart';

/// Whether phones can connect, with the addresses they'd use.
final remoteAccessStatusProvider =
    FutureProvider.autoDispose<RemoteAccessStatus>(
      (ref) => ref.watch(apiClientProvider).getRemoteAccess(),
    );

/// Paired phones and tablets that haven't been revoked.
final pairedDevicesProvider = FutureProvider.autoDispose<List<Device>>(
  (ref) => ref.watch(apiClientProvider).listDevices(),
);
