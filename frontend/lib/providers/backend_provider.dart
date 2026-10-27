import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/api_client.dart';
import '../services/backend_launcher.dart';

/// The launcher that owns the backend process. Created in `main()` so its
/// lifetime is the app's, not a widget's; null where the app doesn't launch a
/// backend itself (mobile, tests).
final backendLauncherProvider = Provider<BackendLauncher?>((ref) => null);

final backendStatusProvider =
    NotifierProvider<BackendStatusNotifier, BackendStatus>(
      BackendStatusNotifier.new,
    );

class BackendStatusNotifier extends Notifier<BackendStatus> {
  @override
  BackendStatus build() {
    final launcher = ref.watch(backendLauncherProvider);
    if (launcher == null) return BackendStatus.ready;

    final sub = launcher.onStatusChange.listen((status) {
      if (status == BackendStatus.ready) {
        // Token first: both rebuild the ApiClient, and it must never pair the
        // new URL with a stale token.
        ref.read(backendApiTokenProvider.notifier).state = launcher.apiToken;
        ref.read(backendBaseUrlProvider.notifier).state = launcher.baseUrl;
      }
      state = status;
    });
    ref.onDispose(sub.cancel);
    return launcher.status;
  }
}

/// The last lines the launcher logged, for the startup and error screens.
final backendLogProvider = NotifierProvider<BackendLogNotifier, List<String>>(
  BackendLogNotifier.new,
);

class BackendLogNotifier extends Notifier<List<String>> {
  static const _maxLines = 200;

  @override
  List<String> build() {
    final launcher = ref.watch(backendLauncherProvider);
    if (launcher == null) return const [];

    final sub = launcher.onLog.listen((line) {
      final lines = [...state, line];
      state = lines.length > _maxLines
          ? lines.sublist(lines.length - _maxLines)
          : lines;
    });
    ref.onDispose(sub.cancel);
    return const [];
  }
}
