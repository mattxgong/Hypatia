import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/study.dart';
import '../../providers/class_provider.dart';
import '../../providers/study_provider.dart';
import '../../services/api_client.dart';
import '../common/error_card.dart';
import '../common/wiki_markdown.dart';
import 'study_actions.dart';

const _sessionSize = 100;

final _ratingKeys = {
  LogicalKeyboardKey.digit1: ReviewRating.again,
  LogicalKeyboardKey.digit2: ReviewRating.hard,
  LogicalKeyboardKey.digit3: ReviewRating.good,
  LogicalKeyboardKey.digit4: ReviewRating.easy,
};

MarkdownStyleSheet studyMarkdownStyle(ThemeData theme, {double scale = 1}) {
  return MarkdownStyleSheet.fromTheme(theme).copyWith(
    p: theme.textTheme.bodyLarge?.copyWith(
      fontSize: (theme.textTheme.bodyLarge?.fontSize ?? 16) * scale,
    ),
  );
}

/// Center-panel review session for one deck: flip a card, then rate it.
class FlashcardReview extends ConsumerStatefulWidget {
  const FlashcardReview({super.key, required this.deckId});

  final String deckId;

  @override
  ConsumerState<FlashcardReview> createState() => _FlashcardReviewState();
}

class _FlashcardReviewState extends ConsumerState<FlashcardReview> {
  final _focusNode = FocusNode();
  List<Flashcard> _queue = [];
  int _reviewed = 0;
  bool _revealed = false;
  bool _loading = true;
  bool _busy = false;
  bool _browsing = false;
  Object? _error;

  String? get _classId => ref.read(currentClassIdProvider);

  @override
  void initState() {
    super.initState();
    _loadDue();
  }

  @override
  void dispose() {
    _focusNode.dispose();
    super.dispose();
  }

  Future<void> _loadDue() async {
    final classId = _classId;
    if (classId == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final cards = await ref
          .read(apiClientProvider)
          .listDueCards(classId, widget.deckId, limit: _sessionSize);
      if (!mounted) return;
      setState(() {
        _queue = cards;
        _reviewed = 0;
        _revealed = false;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _afterChange() {
    final classId = _classId;
    if (classId != null) ref.invalidate(deckListProvider(classId));
  }

  Future<void> _rate(ReviewRating rating) async {
    final classId = _classId;
    if (classId == null || _queue.isEmpty || _busy || !_revealed) return;
    final card = _queue.first;
    setState(() => _busy = true);
    try {
      final updated = await ref
          .read(apiClientProvider)
          .reviewCard(classId, widget.deckId, card.id, rating);
      if (!mounted) return;
      setState(() {
        _queue.removeAt(0);
        // Missed cards come back at the end of this session.
        if (rating == ReviewRating.again) _queue.add(updated);
        _reviewed++;
        _revealed = false;
      });
      _afterChange();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not save review: ${e.detail}')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _replaceCurrent(Flashcard? updated) {
    setState(() {
      if (updated == null) {
        _queue.removeAt(0);
      } else {
        _queue[0] = updated;
      }
    });
    _afterChange();
  }

  KeyEventResult _onKey(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent || _browsing || _queue.isEmpty) {
      return KeyEventResult.ignored;
    }
    if (event.logicalKey == LogicalKeyboardKey.space && !_revealed) {
      setState(() => _revealed = true);
      return KeyEventResult.handled;
    }
    final rating = _ratingKeys[event.logicalKey];
    if (rating != null && _revealed) {
      _rate(rating);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) {
    final classId = ref.watch(currentClassIdProvider);
    final deck = classId == null
        ? null
        : ref
              .watch(deckListProvider(classId))
              .valueOrNull
              ?.where((d) => d.id == widget.deckId)
              .firstOrNull;

    return Focus(
      focusNode: _focusNode,
      autofocus: true,
      onKeyEvent: _onKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _DeckHeader(
            deck: deck,
            browsing: _browsing,
            onToggleBrowse: () => setState(() => _browsing = !_browsing),
            onRefreshed: () {
              _afterChange();
              _loadDue();
            },
          ),
          Expanded(child: _buildBody(context, classId)),
        ],
      ),
    );
  }

  Widget _buildBody(BuildContext context, String? classId) {
    if (classId == null) return const SizedBox.shrink();
    if (_browsing) {
      return _CardBrowser(
        classId: classId,
        deckId: widget.deckId,
        onChanged: () {
          _afterChange();
          _loadDue();
        },
      );
    }
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
        child: ErrorCard(error: _error!, onRetry: _loadDue),
      );
    }
    if (_queue.isEmpty) {
      return _AllCaughtUp(
        reviewed: _reviewed,
        onBrowse: () => setState(() => _browsing = true),
      );
    }

    final theme = Theme.of(context);
    final card = _queue.first;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                '${_queue.length} left in this session'
                '${_reviewed > 0 ? ' · $_reviewed reviewed' : ''}',
                style: theme.textTheme.bodySmall,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              if (card.stale)
                _StaleCardBanner(
                  classId: classId,
                  deckId: widget.deckId,
                  card: card,
                  onChanged: _replaceCurrent,
                ),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      WikiMarkdown(
                        data: card.question,
                        styleSheet: studyMarkdownStyle(theme, scale: 1.15),
                        scrollable: false,
                      ),
                      if (_revealed) ...[
                        const Divider(height: 32),
                        WikiMarkdown(
                          data: card.answer,
                          styleSheet: studyMarkdownStyle(theme),
                          scrollable: false,
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              if (!_revealed)
                Center(
                  child: FilledButton(
                    onPressed: () => setState(() => _revealed = true),
                    child: const Text('Show answer (Space)'),
                  ),
                )
              else
                _RatingButtons(enabled: !_busy, onRate: _rate),
              if (card.pagePaths.isNotEmpty) ...[
                const SizedBox(height: 12),
                Center(
                  child: TextButton.icon(
                    onPressed: () => openWikiPage(ref, card.pagePaths.first),
                    icon: const Icon(Icons.menu_book_outlined, size: 16),
                    label: const Text('Open source page'),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _DeckHeader extends ConsumerWidget {
  const _DeckHeader({
    required this.deck,
    required this.browsing,
    required this.onToggleBrowse,
    required this.onRefreshed,
  });

  final Deck? deck;
  final bool browsing;
  final VoidCallback onToggleBrowse;
  final VoidCallback onRefreshed;

  Future<void> _refreshStale(BuildContext context, WidgetRef ref) async {
    final deck = this.deck;
    if (deck == null) return;
    try {
      final result = await ref
          .read(apiClientProvider)
          .refreshDeck(deck.classId, deck.id);
      onRefreshed();
      if (context.mounted) {
        final remaining = result['remaining_stale'] as int;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Updated ${result['updated']}, removed ${result['removed']}'
              '${remaining > 0 ? ', $remaining of your own cards need a look' : ''}.',
            ),
          ),
        );
      }
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Refresh failed: ${e.detail}')));
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final deck = this.deck;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: theme.dividerColor)),
      ),
      child: Row(
        children: [
          const Icon(Icons.style_outlined, size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(deck?.name ?? 'Deck', style: theme.textTheme.titleMedium),
                if (deck != null)
                  Text(
                    '${deck.dueCount} due · ${deck.cardCount} cards'
                    '${deck.staleCount > 0 ? ' · ${deck.staleCount} out of date' : ''}',
                    style: theme.textTheme.bodySmall,
                  ),
              ],
            ),
          ),
          if (deck != null && deck.staleCount > 0)
            TextButton.icon(
              onPressed: () => _refreshStale(context, ref),
              icon: const Icon(Icons.update, size: 16),
              label: const Text('Update from wiki'),
            ),
          TextButton.icon(
            onPressed: onToggleBrowse,
            icon: Icon(browsing ? Icons.school_outlined : Icons.list, size: 16),
            label: Text(browsing ? 'Review' : 'Browse cards'),
          ),
          if (deck != null)
            PopupMenuButton<String>(
              tooltip: 'Export',
              icon: const Icon(Icons.ios_share, size: 18),
              onSelected: (format) => exportDeck(context, ref, deck, format),
              itemBuilder: (_) => const [
                PopupMenuItem(value: 'anki', child: Text('Export for Anki')),
                PopupMenuItem(value: 'csv', child: Text('Export as CSV')),
              ],
            ),
        ],
      ),
    );
  }
}

class _RatingButtons extends StatelessWidget {
  const _RatingButtons({required this.enabled, required this.onRate});

  final bool enabled;
  final ValueChanged<ReviewRating> onRate;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    Widget button(ReviewRating rating, String label, int key, Color color) {
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4),
        child: OutlinedButton(
          style: OutlinedButton.styleFrom(foregroundColor: color),
          onPressed: enabled ? () => onRate(rating) : null,
          child: Text('$label ($key)'),
        ),
      );
    }

    return Wrap(
      alignment: WrapAlignment.center,
      runSpacing: 8,
      children: [
        button(ReviewRating.again, 'Again', 1, scheme.error),
        button(ReviewRating.hard, 'Hard', 2, scheme.tertiary),
        button(ReviewRating.good, 'Good', 3, scheme.primary),
        button(ReviewRating.easy, 'Easy', 4, scheme.secondary),
      ],
    );
  }
}

class _AllCaughtUp extends StatelessWidget {
  const _AllCaughtUp({required this.reviewed, required this.onBrowse});

  final int reviewed;
  final VoidCallback onBrowse;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.task_alt,
            size: 48,
            color: theme.colorScheme.primary.withValues(alpha: 0.6),
          ),
          const SizedBox(height: 16),
          Text('All caught up', style: theme.textTheme.titleMedium),
          const SizedBox(height: 4),
          Text(
            reviewed > 0
                ? 'You reviewed $reviewed card${reviewed == 1 ? '' : 's'}. '
                      'Come back later for the next ones.'
                : 'No cards are due right now.',
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: 16),
          OutlinedButton(
            onPressed: onBrowse,
            child: const Text('Browse cards'),
          ),
        ],
      ),
    );
  }
}

class _StaleCardBanner extends ConsumerStatefulWidget {
  const _StaleCardBanner({
    required this.classId,
    required this.deckId,
    required this.card,
    required this.onChanged,
  });

  final String classId;
  final String deckId;
  final Flashcard card;

  /// Called with the updated card, or null when it was deleted.
  final ValueChanged<Flashcard?> onChanged;

  @override
  ConsumerState<_StaleCardBanner> createState() => _StaleCardBannerState();
}

class _StaleCardBannerState extends ConsumerState<_StaleCardBanner> {
  bool _busy = false;

  Future<void> _run(String action, Future<Flashcard?> Function() call) async {
    setState(() => _busy = true);
    try {
      final updated = await call();
      if (mounted) widget.onChanged(updated);
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not $action the card: ${e.detail}')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final api = ref.read(apiClientProvider);
    final card = widget.card;
    return Card(
      color: scheme.tertiaryContainer,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        child: Row(
          children: [
            Icon(Icons.update, size: 18, color: scheme.onTertiaryContainer),
            const SizedBox(width: 8),
            const Expanded(
              child: Text('The wiki page behind this card has changed.'),
            ),
            TextButton(
              onPressed: _busy
                  ? null
                  : () => _run(
                      'keep',
                      () => api.updateCard(
                        widget.classId,
                        widget.deckId,
                        card.id,
                        acknowledgeChanges: true,
                      ),
                    ),
              child: const Text('Keep'),
            ),
            TextButton(
              onPressed: _busy
                  ? null
                  : () async {
                      final edited = await showEditCardDialog(
                        context,
                        ref,
                        classId: widget.classId,
                        deckId: widget.deckId,
                        card: card,
                      );
                      if (edited != null && mounted) widget.onChanged(edited);
                    },
              child: const Text('Edit'),
            ),
            TextButton(
              onPressed: _busy
                  ? null
                  : () => _run('delete', () async {
                      await api.deleteCard(
                        widget.classId,
                        widget.deckId,
                        card.id,
                      );
                      return null;
                    }),
              child: const Text('Delete'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Edits a card's text; saving also accepts the current wiki pages as its baseline.
Future<Flashcard?> showEditCardDialog(
  BuildContext context,
  WidgetRef ref, {
  required String classId,
  required String deckId,
  required Flashcard card,
}) {
  final front = TextEditingController(text: card.front);
  final back = TextEditingController(text: card.back);
  final isCloze = card.cardType == CardType.cloze;
  return showDialog<Flashcard>(
    context: context,
    useRootNavigator: false,
    builder: (context) => AlertDialog(
      title: const Text('Edit card'),
      content: SizedBox(
        width: 480,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: front,
              maxLines: null,
              decoration: InputDecoration(
                labelText: isCloze ? 'Text' : 'Front',
                helperText: isCloze
                    ? 'Mark the answer as {{c1::answer}}'
                    : null,
              ),
            ),
            if (!isCloze)
              TextField(
                controller: back,
                maxLines: null,
                decoration: const InputDecoration(labelText: 'Back'),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () async {
            try {
              final updated = await ref
                  .read(apiClientProvider)
                  .updateCard(
                    classId,
                    deckId,
                    card.id,
                    front: front.text,
                    back: isCloze ? null : back.text,
                    acknowledgeChanges: true,
                  );
              if (context.mounted) Navigator.of(context).pop(updated);
            } on ApiException catch (e) {
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text('Save failed: ${e.detail}')),
                );
              }
            }
          },
          child: const Text('Save'),
        ),
      ],
    ),
  ).whenComplete(() {
    front.dispose();
    back.dispose();
  });
}

class _CardBrowser extends ConsumerStatefulWidget {
  const _CardBrowser({
    required this.classId,
    required this.deckId,
    required this.onChanged,
  });

  final String classId;
  final String deckId;
  final VoidCallback onChanged;

  @override
  ConsumerState<_CardBrowser> createState() => _CardBrowserState();
}

class _CardBrowserState extends ConsumerState<_CardBrowser> {
  late Future<List<Flashcard>> _cards = _fetch();

  Future<List<Flashcard>> _fetch() =>
      ref.read(apiClientProvider).listCards(widget.classId, widget.deckId);

  void _reload() {
    setState(() => _cards = _fetch());
    widget.onChanged();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return FutureBuilder<List<Flashcard>>(
      future: _cards,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return Center(
            child: ErrorCard(error: snapshot.error!, onRetry: _reload),
          );
        }
        final cards = snapshot.data;
        if (cards == null) {
          return const Center(child: CircularProgressIndicator());
        }
        if (cards.isEmpty) {
          return const Center(child: Text('This deck has no cards.'));
        }
        return ListView.separated(
          padding: const EdgeInsets.all(16),
          itemCount: cards.length,
          separatorBuilder: (_, _) => const Divider(height: 1),
          itemBuilder: (context, index) {
            final card = cards[index];
            return ListTile(
              title: Text(
                card.question,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              subtitle: Text(
                card.cardType == CardType.cloze ? card.back : card.answer,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall,
              ),
              leading: card.stale
                  ? Tooltip(
                      message: 'The wiki page behind this card has changed',
                      child: Icon(
                        Icons.update,
                        color: theme.colorScheme.tertiary,
                      ),
                    )
                  : const Icon(Icons.style_outlined),
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  IconButton(
                    icon: const Icon(Icons.edit_outlined, size: 18),
                    tooltip: 'Edit card',
                    onPressed: () async {
                      final edited = await showEditCardDialog(
                        context,
                        ref,
                        classId: widget.classId,
                        deckId: widget.deckId,
                        card: card,
                      );
                      if (edited != null) _reload();
                    },
                  ),
                  IconButton(
                    icon: const Icon(Icons.delete_outline, size: 18),
                    tooltip: 'Delete card',
                    onPressed: () async {
                      try {
                        await ref
                            .read(apiClientProvider)
                            .deleteCard(widget.classId, widget.deckId, card.id);
                        _reload();
                      } on ApiException catch (e) {
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text('Delete failed: ${e.detail}'),
                            ),
                          );
                        }
                      }
                    },
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }
}
