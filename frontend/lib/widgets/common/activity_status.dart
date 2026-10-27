import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/source_file.dart';
import '../../models/task_status.dart';
import '../../providers/class_provider.dart';
import '../../providers/file_provider.dart';
import '../../providers/task_provider.dart';
import '../sidebar/source_file_actions.dart';
import '../sidebar/task_indicator.dart';

/// Human names for the backend's task operations.
String describeOperation(String operation) => switch (operation) {
  'ingest' => 'Adding to the wiki',
  'rebuild' => 'Rebuilding the wiki',
  'flashcards' || 'deck' => 'Making flashcards',
  'quiz' => 'Making a quiz',
  _ => operation,
};

/// What the backend is working on for the open Class, shown in the top bar
/// where it stays visible with the sidebar collapsed. Click for details.
class ActivityStatus extends ConsumerWidget {
  const ActivityStatus({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final classId = ref.watch(currentClassIdProvider);
    final tasks = ref.watch(taskListProvider).activeTasks;
    final files = classId == null
        ? const <SourceFile>[]
        : ref.watch(fileListProvider(classId)).valueOrNull ?? const [];

    final summary = _summary(tasks, files);
    if (summary == null) {
      return Text('Hypatia', style: theme.textTheme.titleSmall);
    }

    return Semantics(
      liveRegion: true,
      button: true,
      label: summary,
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => showActiveTasksDialog(context),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  summary,
                  style: theme.textTheme.bodySmall,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String? _summary(List<TaskStatus> tasks, List<SourceFile> files) {
    if (tasks.isNotEmpty) {
      final task = tasks.first;
      final progress = task.progress == null ? '' : ' · ${task.progress}%';
      final more = tasks.length > 1 ? ' (+${tasks.length - 1} more)' : '';
      final detail = task.message.isNotEmpty
          ? task.message
          : describeOperation(task.operation);
      return '$detail$progress$more';
    }
    final converting = files.where((f) => f.isConverting).length;
    if (converting > 0) {
      return 'Converting $converting file${converting == 1 ? '' : 's'}…';
    }
    return null;
  }
}

/// Tells the user when a source file finishes processing or fails, wherever
/// they are in the app. Wraps the home screen.
class SourceFileEvents extends ConsumerWidget {
  const SourceFileEvents({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final classId = ref.watch(currentClassIdProvider);
    if (classId != null) {
      // Polls while anything is processing, including work already running
      // when the app opened.
      ref.watch(filePollingProvider(classId));
      ref.listen(fileListProvider(classId), (previous, next) {
        final before = {
          for (final f in previous?.valueOrNull ?? const <SourceFile>[])
            f.id: f,
        };
        for (final file in next.valueOrNull ?? const <SourceFile>[]) {
          final old = before[file.id];
          if (old == null || !_busy(old)) continue;
          if (file.status == FileStatus.error) {
            _notifyFailed(context, ref, classId, file);
          } else if (!_busy(file) && file.status == FileStatus.ready) {
            _notify(context, '${file.originalFilename} is in your wiki now');
          }
        }
      });
    }
    return child;
  }

  static bool _busy(SourceFile f) =>
      f.isConverting || f.isSummarizing || f.status == FileStatus.processing;

  void _notify(BuildContext context, String message) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  void _notifyFailed(
    BuildContext context,
    WidgetRef ref,
    String classId,
    SourceFile file,
  ) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          '${file.originalFilename} failed: '
          '${file.errorMessage ?? 'processing error'}',
        ),
        duration: const Duration(seconds: 8),
        // A SnackBar with an action otherwise stays until dismissed.
        persist: false,
        action: SnackBarAction(
          label: 'Retry',
          onPressed: () => retrySourceFile(context, ref, classId, file),
        ),
      ),
    );
  }
}
