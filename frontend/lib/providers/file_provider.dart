import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/source_file.dart';
import '../services/api_client.dart';
import 'task_provider.dart';
import 'wiki_provider.dart';

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
    ref.listen(fileListProvider(arg), (prev, next) {
      final files = next.valueOrNull ?? [];
      final hasProcessing = files.any((f) => f.isConverting || f.isSummarizing);
      final summarizingBefore = {
        for (final f in prev?.valueOrNull ?? <SourceFile>[])
          if (f.isSummarizing) f.id,
      };
      if (files.any(
        (f) => summarizingBefore.contains(f.id) && !f.isSummarizing,
      )) {
        ref.invalidate(wikiTreeProvider(arg));
      }

      if (hasProcessing && _timer == null) {
        _startPolling();
      } else if (!hasProcessing && _timer != null) {
        _stopPolling();
        ref.invalidate(wikiTreeProvider(arg));
      }
    });
    return false;
  }

  void _startPolling() {
    if (_timer != null) return;
    state = true;
    _timer = Timer.periodic(const Duration(seconds: 3), (_) {
      ref.invalidate(fileListProvider(arg));
      ref.read(taskListProvider.notifier).fetchTasks();
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
