import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/source_file.dart';
import '../services/api_client.dart';

final fileListProvider = FutureProvider.family<List<SourceFile>, String>((
  ref,
  classId,
) async {
  final apiClient = ref.read(apiClientProvider);
  return apiClient.listFiles(classId);
});

final filePollingProvider =
    NotifierProvider.family<FilePollingNotifier, bool, String>(
      FilePollingNotifier.new,
    );

class FilePollingNotifier extends FamilyNotifier<bool, String> {
  Timer? _timer;

  @override
  bool build(String arg) {
    ref.onDispose(() => _timer?.cancel());
    ref.listen(fileListProvider(arg), (_, next) {
      final files = next.valueOrNull ?? [];
      final hasProcessing = files.any(
        (f) =>
            f.status == FileStatus.processing || f.status == FileStatus.pending,
      );

      if (hasProcessing && _timer == null) {
        _startPolling();
      } else if (!hasProcessing && _timer != null) {
        _stopPolling();
      }
    });
    return false;
  }

  void _startPolling() {
    if (_timer != null) return;
    state = true;
    _timer = Timer.periodic(const Duration(seconds: 3), (_) {
      ref.invalidate(fileListProvider(arg));
    });
  }

  void _stopPolling() {
    _timer?.cancel();
    _timer = null;
    state = false;
  }

  void startPolling() => _startPolling();

  void stopPolling() => _stopPolling();
}
