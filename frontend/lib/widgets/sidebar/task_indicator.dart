import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/task_status.dart';
import '../../providers/task_provider.dart';

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
          onPressed: () => _showTasksDialog(context, ref, taskState),
          iconSize: 18,
          constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
          padding: EdgeInsets.zero,
          color: theme.colorScheme.primary,
        ),
      ),
    );
  }

  void _showTasksDialog(
    BuildContext context,
    WidgetRef ref,
    TaskListState taskState,
  ) {
    showDialog<void>(
      context: context,
      builder: (context) => _TaskListDialog(tasks: taskState.activeTasks),
    );
  }
}

class _TaskListDialog extends ConsumerWidget {
  const _TaskListDialog({required this.tasks});

  final List<TaskStatus> tasks;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final currentTasks = ref.watch(taskListProvider).activeTasks;
    final displayTasks = currentTasks.isNotEmpty ? currentTasks : tasks;

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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(task.operation, style: theme.textTheme.titleSmall),
            ),
            Text('${task.progress}%', style: theme.textTheme.bodySmall),
            const SizedBox(width: 8),
            SizedBox(
              width: 24,
              height: 24,
              child: IconButton(
                icon: const Icon(Icons.cancel_outlined, size: 16),
                onPressed: () =>
                    ref.read(taskListProvider.notifier).cancelTask(task.taskId),
                padding: EdgeInsets.zero,
                tooltip: 'Cancel',
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        LinearProgressIndicator(value: task.progress / 100),
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
