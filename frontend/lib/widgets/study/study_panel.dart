import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/study.dart';
import '../../providers/class_provider.dart';
import '../../providers/study_provider.dart';
import '../common/error_card.dart';
import 'generate_study_dialog.dart';
import 'study_actions.dart';

/// Sidebar list of the current class's flashcard decks and practice quizzes.
class StudyPanel extends ConsumerWidget {
  const StudyPanel({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final classId = ref.watch(currentClassIdProvider);
    if (classId == null) {
      return const Center(child: Text('Select a class'));
    }
    final decksAsync = ref.watch(deckListProvider(classId));
    final quizzesAsync = ref.watch(quizListProvider(classId));
    final selection = ref.watch(studySelectionProvider);
    final jobs = ref
        .watch(studyJobsProvider)
        .where((j) => j.classId == classId)
        .toList();

    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          child: FilledButton.tonalIcon(
            onPressed: () => showGenerateStudyDialog(context),
            icon: const Icon(Icons.auto_awesome_outlined, size: 18),
            label: const Text('Create study material'),
          ),
        ),
        for (final job in jobs) _JobTile(job: job),
        _Section(
          title: 'Flashcard decks',
          icon: Icons.style_outlined,
          count: decksAsync.valueOrNull?.length,
          child: decksAsync.when(
            loading: () => const _Loading(),
            error: (e, _) => _SectionError(
              error: e,
              onRetry: () => ref.invalidate(deckListProvider(classId)),
            ),
            data: (decks) => decks.isEmpty
                ? const _Empty('No decks yet')
                : Column(
                    children: [
                      for (final deck in decks)
                        _DeckTile(
                          deck: deck,
                          selected:
                              selection ==
                              StudySelection(StudyKind.deck, deck.id),
                        ),
                    ],
                  ),
          ),
        ),
        _Section(
          title: 'Practice quizzes',
          icon: Icons.quiz_outlined,
          count: quizzesAsync.valueOrNull?.length,
          child: quizzesAsync.when(
            loading: () => const _Loading(),
            error: (e, _) => _SectionError(
              error: e,
              onRetry: () => ref.invalidate(quizListProvider(classId)),
            ),
            data: (quizzes) => quizzes.isEmpty
                ? const _Empty('No quizzes yet')
                : Column(
                    children: [
                      for (final quiz in quizzes)
                        _QuizTile(
                          quiz: quiz,
                          selected:
                              selection ==
                              StudySelection(StudyKind.quiz, quiz.id),
                        ),
                    ],
                  ),
          ),
        ),
      ],
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({
    required this.title,
    required this.icon,
    required this.count,
    required this.child,
  });

  final String title;
  final IconData icon;
  final int? count;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ExpansionTile(
      leading: Icon(icon, size: 18),
      title: Text(
        count == null ? title : '$title ($count)',
        style: theme.textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w600),
      ),
      dense: true,
      tilePadding: const EdgeInsets.symmetric(horizontal: 8),
      childrenPadding: const EdgeInsets.only(left: 8),
      initiallyExpanded: true,
      children: [child],
    );
  }
}

class _JobTile extends ConsumerWidget {
  const _JobTile({required this.job});

  final StudyJob job;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final notifier = ref.read(studyJobsProvider.notifier);
    final error = job.error;
    final progress = job.progress;
    return ListTile(
      dense: true,
      visualDensity: VisualDensity.compact,
      leading: error != null
          ? Icon(Icons.error_outline, size: 18, color: theme.colorScheme.error)
          : const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
      title: Text(
        job.label,
        style: theme.textTheme.bodySmall,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Text(
        error ??
            (job.message.isEmpty
                ? 'Writing with AI...'
                : '${job.message}${progress == null ? '' : ' ($progress%)'}'),
        style: theme.textTheme.labelSmall?.copyWith(
          color: error == null ? null : theme.colorScheme.error,
        ),
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
      trailing: IconButton(
        icon: Icon(
          error == null ? Icons.cancel_outlined : Icons.close,
          size: 16,
        ),
        tooltip: error == null ? 'Cancel' : 'Dismiss',
        visualDensity: VisualDensity.compact,
        onPressed: () => error == null
            ? notifier.cancel(job.taskId)
            : notifier.dismiss(job.taskId),
      ),
    );
  }
}

class _Loading extends StatelessWidget {
  const _Loading();

  @override
  Widget build(BuildContext context) => const Padding(
    padding: EdgeInsets.all(8),
    child: Center(
      child: SizedBox(
        width: 16,
        height: 16,
        child: CircularProgressIndicator(strokeWidth: 2),
      ),
    ),
  );
}

class _Empty extends StatelessWidget {
  const _Empty(this.message);

  final String message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Text(
        message,
        style: theme.textTheme.bodySmall?.copyWith(
          color: theme.colorScheme.onSurfaceVariant,
        ),
      ),
    );
  }
}

class _SectionError extends StatelessWidget {
  const _SectionError({required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(8),
    child: ErrorCard(error: error, compact: true, onRetry: onRetry),
  );
}

class _StaleIcon extends StatelessWidget {
  const _StaleIcon(this.count, this.noun);

  final int count;
  final String noun;

  @override
  Widget build(BuildContext context) => Tooltip(
    message:
        '$count $noun${count == 1 ? '' : 's'} out of date: '
        'the wiki changed since they were made',
    child: Icon(
      Icons.update,
      size: 16,
      color: Theme.of(context).colorScheme.tertiary,
    ),
  );
}

class _DeckTile extends ConsumerWidget {
  const _DeckTile({required this.deck, required this.selected});

  final Deck deck;
  final bool selected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return ListTile(
      dense: true,
      visualDensity: VisualDensity.compact,
      selected: selected,
      selectedTileColor: theme.colorScheme.primaryContainer.withValues(
        alpha: 0.3,
      ),
      title: Text(
        deck.name,
        style: theme.textTheme.bodySmall,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Text(
        '${deck.dueCount} due · ${deck.cardCount} cards',
        style: theme.textTheme.labelSmall,
      ),
      onTap: () => ref.read(studySelectionProvider.notifier).state =
          StudySelection(StudyKind.deck, deck.id),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (deck.staleCount > 0) _StaleIcon(deck.staleCount, 'card'),
          PopupMenuButton<String>(
            tooltip: 'Deck actions',
            iconSize: 16,
            onSelected: (action) {
              switch (action) {
                case 'csv':
                case 'anki':
                  exportDeck(context, ref, deck, action);
                case 'delete':
                  deleteDeck(context, ref, deck);
              }
            },
            itemBuilder: (_) => const [
              PopupMenuItem(value: 'anki', child: Text('Export for Anki')),
              PopupMenuItem(value: 'csv', child: Text('Export as CSV')),
              PopupMenuItem(value: 'delete', child: Text('Delete deck')),
            ],
          ),
        ],
      ),
    );
  }
}

class _QuizTile extends ConsumerWidget {
  const _QuizTile({required this.quiz, required this.selected});

  final QuizSummary quiz;
  final bool selected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final last = quiz.lastScore;
    final lastMax = quiz.lastMaxScore;
    final score = last == null || lastMax == null
        ? 'not taken'
        : 'last ${formatScore(last)}/${formatScore(lastMax)}';
    return ListTile(
      dense: true,
      visualDensity: VisualDensity.compact,
      selected: selected,
      selectedTileColor: theme.colorScheme.primaryContainer.withValues(
        alpha: 0.3,
      ),
      title: Text(
        quiz.name,
        style: theme.textTheme.bodySmall,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Text(
        '${quiz.questionCount} questions · $score',
        style: theme.textTheme.labelSmall,
      ),
      onTap: () => ref.read(studySelectionProvider.notifier).state =
          StudySelection(StudyKind.quiz, quiz.id),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (quiz.staleCount > 0) _StaleIcon(quiz.staleCount, 'question'),
          IconButton(
            icon: const Icon(Icons.delete_outline, size: 16),
            tooltip: 'Delete quiz',
            visualDensity: VisualDensity.compact,
            onPressed: () => deleteQuiz(context, ref, quiz),
          ),
        ],
      ),
    );
  }
}
