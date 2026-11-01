import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/study.dart';
import '../../models/wiki_page.dart';
import '../../providers/class_provider.dart';
import '../../providers/study_provider.dart';
import '../../providers/wiki_provider.dart';

/// Wiki pages ordered by how often they came up in misses, most first.
List<(String, int)> weakPages(Iterable<List<String>> missedPagePaths) {
  final counts = <String, int>{};
  for (final paths in missedPagePaths) {
    for (final path in paths.toSet()) {
      counts[path] = (counts[path] ?? 0) + 1;
    }
  }
  return counts.entries.map((e) => (e.key, e.value)).toList()
    ..sort((a, b) => b.$2.compareTo(a.$2));
}

/// "in 10 minutes", "in 3 hours", "tomorrow", "in 4 days".
String describeNextDue(DateTime due, DateTime now) {
  final wait = due.difference(now);
  if (wait.inMinutes < 1) return 'now';
  if (wait.inMinutes < 60) {
    return 'in ${wait.inMinutes} minute${wait.inMinutes == 1 ? '' : 's'}';
  }
  if (wait.inHours < 24) {
    return 'in ${wait.inHours} hour${wait.inHours == 1 ? '' : 's'}';
  }
  final days = DateUtils.dateOnly(
    due,
  ).difference(DateUtils.dateOnly(now)).inDays;
  return days == 1 ? 'tomorrow' : 'in $days days';
}

/// What a finished flashcard session or quiz achieved, and what to look at next.
///
/// Give [ratings] for a flashcard session, or [score] and [maxScore] for a quiz.
class SessionSummary extends ConsumerWidget {
  const SessionSummary({
    super.key,
    this.ratings,
    this.score,
    this.maxScore,
    this.weak = const [],
    this.dueNow = 0,
    this.nextDue,
    this.actions = const [],
  });

  final Map<ReviewRating, int>? ratings;
  final double? score;
  final double? maxScore;

  /// From [weakPages]; the first three are shown.
  final List<(String, int)> weak;

  /// Cards still due in this deck after the session.
  final int dueNow;
  final DateTime? nextDue;
  final List<Widget> actions;

  static const _maxWeakPages = 3;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final ratings = this.ratings;
    final reviewed = ratings?.values.fold(0, (a, b) => a + b) ?? 0;
    final score = this.score;
    final maxScore = this.maxScore;
    final perfect = ratings != null
        ? reviewed > 0 && (ratings[ReviewRating.again] ?? 0) == 0
        : score != null && score == maxScore;

    final classId = ref.watch(currentClassIdProvider);
    final pages = classId == null
        ? null
        : ref.watch(wikiTreeProvider(classId)).valueOrNull;
    final titles = {
      for (final page in pages ?? const <WikiPageSummary>[])
        page.path: page.title,
    };

    final icon = Icon(
      perfect ? Icons.emoji_events_outlined : Icons.task_alt,
      size: 48,
      color: theme.colorScheme.primary.withValues(alpha: 0.7),
    );
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        // A small pop-in, skipped when the platform asks for less motion.
        if (MediaQuery.of(context).disableAnimations)
          icon
        else
          TweenAnimationBuilder<double>(
            tween: Tween(begin: 0.6, end: 1),
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeOutBack,
            builder: (context, scale, child) =>
                Transform.scale(scale: scale, child: child),
            child: icon,
          ),
        const SizedBox(height: 12),
        Text(
          ratings != null
              ? 'Reviewed $reviewed card${reviewed == 1 ? '' : 's'}'
              : 'You earned ${formatScore(score ?? 0)} of '
                    '${formatScore(maxScore ?? 0)} ${maxScore == 1 ? 'point' : 'points'}',
          style: theme.textTheme.titleMedium,
        ),
        if (ratings != null) ...[
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 4,
            alignment: WrapAlignment.center,
            children: [
              for (final rating in ReviewRating.values)
                if ((ratings[rating] ?? 0) > 0)
                  Chip(
                    label: Text('${_ratingLabel(rating)}: ${ratings[rating]}'),
                    visualDensity: VisualDensity.compact,
                  ),
            ],
          ),
        ],
        const SizedBox(height: 12),
        if (weak.isEmpty)
          Text(
            perfect ? 'No misses this time.' : 'No wiki pages to revisit.',
            style: theme.textTheme.bodyMedium,
          )
        else ...[
          Text('Worth another look:', style: theme.textTheme.labelLarge),
          for (final (path, misses) in weak.take(_maxWeakPages))
            TextButton.icon(
              onPressed: () => openWikiPage(ref, path),
              icon: const Icon(Icons.menu_book_outlined, size: 16),
              label: Text(
                '${titles[path] ?? path.split('/').last} '
                '($misses miss${misses == 1 ? '' : 'es'})',
              ),
            ),
        ],
        if (ratings != null) ...[
          const SizedBox(height: 8),
          Text(
            _dueText(dueNow, nextDue, DateTime.now()),
            style: theme.textTheme.bodyMedium,
            textAlign: TextAlign.center,
          ),
        ],
        if (actions.isNotEmpty) ...[
          const SizedBox(height: 16),
          Wrap(spacing: 8, runSpacing: 8, children: actions),
        ],
      ],
    );
  }

  static String _ratingLabel(ReviewRating rating) => switch (rating) {
    ReviewRating.again => 'Again',
    ReviewRating.hard => 'Hard',
    ReviewRating.good => 'Good',
    ReviewRating.easy => 'Easy',
  };

  static String _dueText(int dueNow, DateTime? nextDue, DateTime now) {
    if (dueNow > 0) {
      return '$dueNow more card${dueNow == 1 ? ' is' : 's are'} due now.';
    }
    if (nextDue == null) return 'No reviews scheduled yet.';
    return 'Next review ${describeNextDue(nextDue, now)}.';
  }
}
