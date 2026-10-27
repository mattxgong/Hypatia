import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/wiki_provider.dart';
import '../../services/api_client.dart';
import '../../utils/frontmatter.dart';
import '../common/error_card.dart';
import '../common/wiki_markdown.dart';

final sourceViewerRequestProvider = StateProvider<SourceViewerRequest?>(
  (ref) => null,
);

class SourceViewerRequest {
  const SourceViewerRequest({required this.fileRef, required this.location});
  final String fileRef;
  final String location;
}

class WikiViewer extends ConsumerStatefulWidget {
  const WikiViewer({super.key});

  @override
  ConsumerState<WikiViewer> createState() => _WikiViewerState();
}

class _WikiViewerState extends ConsumerState<WikiViewer> {
  bool _saving = false;

  @override
  Widget build(BuildContext context) {
    final pageAsync = ref.watch(currentWikiPageProvider);
    final theme = Theme.of(context);

    return pageAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: ErrorCard(
          error: e,
          onRetry: () => ref.invalidate(currentWikiPageProvider),
        ),
      ),
      data: (page) {
        if (page == null) {
          return Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  Icons.menu_book_outlined,
                  size: 48,
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.3),
                ),
                const SizedBox(height: 16),
                Text(
                  'Select a wiki page from the sidebar',
                  style: theme.textTheme.bodyLarge?.copyWith(
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                  ),
                ),
              ],
            ),
          );
        }

        final key = (classId: page.classId, path: page.path);
        final editing = ref.watch(
          wikiEditDraftsProvider.select((drafts) => drafts.containsKey(key)),
        );
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildHeader(page.title, page.updatedAt, key, editing),
            Expanded(
              child: editing
                  ? _DraftEditor(key: ValueKey(key), pageKey: key)
                  : _buildViewer(theme, page.content),
            ),
          ],
        );
      },
    );
  }

  Widget _buildHeader(
    String title,
    DateTime updatedAt,
    WikiPageKey key,
    bool editing,
  ) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: theme.dividerColor)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: theme.textTheme.titleMedium),
                Text(
                  'Last updated: ${_formatDate(updatedAt)}',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                  ),
                ),
              ],
            ),
          ),
          if (editing) ...[
            TextButton(
              onPressed: _saving ? null : () => _cancelEdit(key),
              child: const Text('Cancel'),
            ),
            const SizedBox(width: 8),
            FilledButton(
              onPressed: _saving ? null : () => _saveEdit(key),
              child: _saving
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Save'),
            ),
          ] else
            IconButton(
              icon: const Icon(Icons.edit_outlined, size: 18),
              onPressed: () => _startEdit(key),
              tooltip: 'Edit page',
            ),
        ],
      ),
    );
  }

  Widget _buildViewer(ThemeData theme, String content) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
      child: WikiMarkdown(
        data: stripFrontmatter(content),
        styleSheet: MarkdownStyleSheet.fromTheme(theme).copyWith(
          h1: theme.textTheme.headlineMedium,
          h2: theme.textTheme.titleLarge,
          h3: theme.textTheme.titleMedium,
          p: theme.textTheme.bodyMedium,
          code: theme.textTheme.bodySmall?.copyWith(
            fontFamily: 'monospace',
            backgroundColor: theme.colorScheme.surfaceContainerHighest,
          ),
        ),
      ),
    );
  }

  void _startEdit(WikiPageKey key) {
    final page = ref.read(currentWikiPageProvider).valueOrNull;
    if (page == null) return;
    _setDraft(key, page.content);
  }

  void _cancelEdit(WikiPageKey key) => _setDraft(key, null);

  void _setDraft(WikiPageKey key, String? text) {
    final notifier = ref.read(wikiEditDraftsProvider.notifier);
    notifier.state = {
      for (final entry in notifier.state.entries)
        if (entry.key != key) entry.key: entry.value,
      key: ?text,
    };
  }

  Future<void> _saveEdit(WikiPageKey key) async {
    if (_saving) return;
    final text = ref.read(wikiEditDraftsProvider)[key];
    if (text == null) return;

    setState(() => _saving = true);
    try {
      final apiClient = ref.read(apiClientProvider);
      await apiClient.updateWikiPage(key.classId, key.path, text);
      _setDraft(key, null);
      ref.invalidate(currentWikiPageProvider);
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Save failed: ${e.detail}')));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  String _formatDate(DateTime date) {
    return '${date.year}-${date.month.toString().padLeft(2, '0')}-'
        '${date.day.toString().padLeft(2, '0')}';
  }
}

/// Edits one page's draft. Keyed by page, so switching pages gets a fresh
/// controller seeded from that page's own draft.
class _DraftEditor extends ConsumerStatefulWidget {
  const _DraftEditor({super.key, required this.pageKey});

  final WikiPageKey pageKey;

  @override
  ConsumerState<_DraftEditor> createState() => _DraftEditorState();
}

class _DraftEditorState extends ConsumerState<_DraftEditor> {
  late final TextEditingController _controller = TextEditingController(
    text: ref.read(wikiEditDraftsProvider)[widget.pageKey] ?? '',
  );

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onChanged(String text) {
    final notifier = ref.read(wikiEditDraftsProvider.notifier);
    if (!notifier.state.containsKey(widget.pageKey)) return;
    notifier.state = {...notifier.state, widget.pageKey: text};
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: TextField(
        controller: _controller,
        onChanged: _onChanged,
        maxLines: null,
        expands: true,
        textAlignVertical: TextAlignVertical.top,
        style: const TextStyle(fontFamily: 'monospace', fontSize: 14),
        decoration: const InputDecoration(
          border: OutlineInputBorder(),
          contentPadding: EdgeInsets.all(12),
        ),
      ),
    );
  }
}
