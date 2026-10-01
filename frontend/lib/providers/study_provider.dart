import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/study.dart';
import '../services/api_client.dart';
import 'wiki_provider.dart';

enum SidebarMode { wiki, study }

enum StudyKind { deck, quiz }

class StudySelection {
  const StudySelection(this.kind, this.id);

  final StudyKind kind;
  final String id;

  @override
  bool operator ==(Object other) =>
      other is StudySelection && other.kind == kind && other.id == id;

  @override
  int get hashCode => Object.hash(kind, id);
}

final sidebarModeProvider = StateProvider<SidebarMode>(
  (ref) => SidebarMode.wiki,
);

/// The deck or quiz shown in the center panel; null shows the wiki viewer.
final studySelectionProvider = StateProvider<StudySelection?>((ref) => null);

/// Shows a wiki page in the center panel, leaving any study view.
void openWikiPage(WidgetRef ref, String path) {
  ref.read(currentWikiPagePathProvider.notifier).state = path;
  ref.read(studySelectionProvider.notifier).state = null;
}

final deckListProvider = FutureProvider.family<List<Deck>, String>((
  ref,
  classId,
) async {
  return ref.read(apiClientProvider).listDecks(classId);
});

final quizListProvider = FutureProvider.family<List<QuizSummary>, String>((
  ref,
  classId,
) async {
  return ref.read(apiClientProvider).listQuizzes(classId);
});

final quizProvider =
    FutureProvider.family<Quiz, ({String classId, String quizId})>((
      ref,
      key,
    ) async {
      return ref.read(apiClientProvider).getQuiz(key.classId, key.quizId);
    });

/// An AI generation task the Study panel shows until it finishes.
class StudyJob {
  const StudyJob({
    required this.taskId,
    required this.classId,
    required this.kind,
    required this.label,
    this.progress,
    this.message = '',
    this.error,
  });

  final String taskId;
  final String classId;
  final StudyKind kind;
  final String label;
  final int? progress;
  final String message;

  /// Set when the task failed; the job stays listed until dismissed.
  final String? error;

  StudyJob copyWith({int? progress, String? message, String? error}) =>
      StudyJob(
        taskId: taskId,
        classId: classId,
        kind: kind,
        label: label,
        progress: progress ?? this.progress,
        message: message ?? this.message,
        error: error ?? this.error,
      );
}

class StudyJobsNotifier extends Notifier<List<StudyJob>> {
  static const pollInterval = Duration(seconds: 2);
  Timer? _timer;

  @override
  List<StudyJob> build() {
    ref.onDispose(() => _timer?.cancel());
    return const [];
  }

  void track(StudyJob job) {
    state = [...state, job];
    _timer ??= Timer.periodic(pollInterval, (_) => poll());
  }

  void dismiss(String taskId) {
    state = [
      for (final job in state)
        if (job.taskId != taskId) job,
    ];
  }

  Future<void> cancel(String taskId) async {
    try {
      await ref.read(apiClientProvider).cancelTask(taskId);
    } on ApiException {
      // Already finished or forgotten by the backend; dropping it is enough.
    }
    dismiss(taskId);
  }

  Future<void> poll() async {
    final api = ref.read(apiClientProvider);
    final updates = <String, StudyJob?>{};
    for (final job in state.where((j) => j.error == null)) {
      try {
        final task = await api.getTask(job.taskId);
        switch (task.status) {
          case 'running':
            updates[job.taskId] = job.copyWith(
              progress: task.progress,
              message: task.message,
            );
          case 'complete':
            ref.invalidate(
              job.kind == StudyKind.deck
                  ? deckListProvider(job.classId)
                  : quizListProvider(job.classId),
            );
            updates[job.taskId] = null;
          case 'failed':
            updates[job.taskId] = job.copyWith(
              error: task.error ?? 'Generation failed',
            );
          default:
            updates[job.taskId] = null;
        }
      } on ApiException catch (e) {
        if (e.statusCode == 404) {
          updates[job.taskId] = job.copyWith(
            error: 'Lost track of this job; the backend may have restarted.',
          );
        }
      }
    }
    // Rebuild from the current state so jobs tracked during the poll survive.
    state = [
      for (final job in state)
        if (!updates.containsKey(job.taskId)) job else ?updates[job.taskId],
    ];
    if (!state.any((j) => j.error == null)) {
      _timer?.cancel();
      _timer = null;
    }
  }
}

final studyJobsProvider = NotifierProvider<StudyJobsNotifier, List<StudyJob>>(
  StudyJobsNotifier.new,
);
