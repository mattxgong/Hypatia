import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/task_status.dart';
import '../services/api_client.dart';

class TaskListState {
  const TaskListState({this.tasks = const []});

  final List<TaskStatus> tasks;

  bool get hasActiveTasks => tasks.any((t) => t.isActive);
  int get activeCount => tasks.where((t) => t.isActive).length;
  List<TaskStatus> get activeTasks => tasks.where((t) => t.isActive).toList();
}

class TaskListNotifier extends Notifier<TaskListState> {
  Timer? _pollTimer;
  static const _pollInterval = Duration(seconds: 3);

  @override
  TaskListState build() {
    ref.onDispose(() => _pollTimer?.cancel());
    return const TaskListState();
  }

  Future<void> fetchTasks() async {
    final api = ref.read(apiClientProvider);
    try {
      final tasks = await api.listTasks();
      state = TaskListState(tasks: tasks);
      _updatePolling();
    } catch (_) {
      // Silently ignore polling errors to avoid spamming the UI.
    }
  }

  void startPolling() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(_pollInterval, (_) => fetchTasks());
    fetchTasks();
  }

  void stopPolling() {
    _pollTimer?.cancel();
    _pollTimer = null;
  }

  void _updatePolling() {
    if (state.hasActiveTasks && _pollTimer == null) {
      startPolling();
    } else if (!state.hasActiveTasks && _pollTimer != null) {
      stopPolling();
    }
  }

  Future<void> cancelTask(String taskId) async {
    final api = ref.read(apiClientProvider);
    await api.cancelTask(taskId);
    await fetchTasks();
  }
}

final taskListProvider = NotifierProvider<TaskListNotifier, TaskListState>(
  TaskListNotifier.new,
);
