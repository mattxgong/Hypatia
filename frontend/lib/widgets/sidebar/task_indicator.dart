import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/task_status.dart';
import '../../providers/task_provider.dart';
import '../common/activity_status.dart';

class TaskIndicator extends ConsumerWidget {
  const TaskIndicator({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final taskState = ref.watch(taskListProvider);
    if (!taskState.hasActiveTasks) return const SizedBox.shrink();

    final theme = Theme.of(context);
    return Tooltip(
      message: '${taskState.activeCount} task(s) running',
      child: Badge(
        label: Text('${taskState.activeCount}'),
        child: IconButton(
          icon: const Icon(Icons.pending_actions, size: 18),
          onPressed: () => showActiveTasksDialog(context),
          iconSize: 18,
          constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
          padding: EdgeInsets.zero,
          color: theme.colorScheme.primary,
        ),
      ),
    );
  }
}

/// Lists the backend's running tasks, live, with a Cancel button for each.
void showActiveTasksDialog(BuildContext context) {
  showDialog<void>(
    context: context,
    builder: (context) => const _TaskListDialog(),
  );
}

class _TaskListDialog extends ConsumerWidget {
  const _TaskListDialog();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final displayTasks = ref.watch(taskListProvider).activeTasks;

    return AlertDialog(
      title: const Text('Active Tasks'),
      content: SizedBox(
        width: 400,
        child: displayTasks.isEmpty
            ? const Text('No active tasks.')
            : ListView.separated(
                shrinkWrap: true,
                itemCount: displayTasks.length,
                separatorBuilder: (_, _) => const SizedBox(height: 12),
                itemBuilder: (context, index) {
                  final task = displayTasks[index];
                  return _TaskTile(task: task);
                },
              ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }
}

class _TaskTile extends ConsumerWidget {
  const _TaskTile({required this.task});

  final TaskStatus task;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final progress = task.progress;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                describeOperation(task.operation),
                style: theme.textTheme.titleSmall,
              ),
            ),
            if (progress != null)
              Text('$progress%', style: theme.textTheme.bodySmall),
            const SizedBox(width: 8),
            IconButton(
              icon: const Icon(Icons.cancel_outlined, size: 18),
              onPressed: () =>
                  ref.read(taskListProvider.notifier).cancelTask(task.taskId),
              tooltip: 'Cancel',
              constraints: const BoxConstraints(minWidth: 40, minHeight: 40),
            ),
          ],
        ),
        const SizedBox(height: 4),
        LinearProgressIndicator(
          value: progress == null ? null : progress / 100,
        ),
        if (task.message.isNotEmpty) ...[
          const SizedBox(height: 2),
          Text(
            task.message,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ],
    );
  }
}
