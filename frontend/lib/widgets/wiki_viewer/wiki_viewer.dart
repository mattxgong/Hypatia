import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../providers/class_provider.dart';
import '../../providers/wiki_provider.dart';
import '../../services/api_client.dart';

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
  bool _editing = false;
  final _editController = TextEditingController();
  bool _saving = false;

  @override
  void dispose() {
    _editController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final pageAsync = ref.watch(currentWikiPageProvider);
    final theme = Theme.of(context);

    return pageAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Error: $e')),
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

        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildHeader(page.title, page.updatedAt),
            Expanded(
              child: _editing
                  ? _buildEditor()
                  : _buildViewer(theme, page.content),
            ),
          ],
        );
      },
    );
  }

  Widget _buildHeader(String title, DateTime updatedAt) {
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
          if (_editing) ...[
            TextButton(
              onPressed: _saving ? null : _cancelEdit,
              child: const Text('Cancel'),
            ),
            const SizedBox(width: 8),
            FilledButton(
              onPressed: _saving ? null : _saveEdit,
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
              onPressed: _startEdit,
              tooltip: 'Edit page',
            ),
        ],
      ),
    );
  }

  Widget _buildViewer(ThemeData theme, String content) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
      child: Markdown(
        data: _preprocessWikiLinks(content),
        selectable: true,
        onTapLink: (text, href, title) => _handleLink(href),
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

  Widget _buildEditor() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: TextField(
        controller: _editController,
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

  void _startEdit() {
    final page = ref.read(currentWikiPageProvider).valueOrNull;
    if (page == null) return;
    _editController.text = page.content;
    setState(() => _editing = true);
  }

  void _cancelEdit() {
    setState(() => _editing = false);
  }

  Future<void> _saveEdit() async {
    if (_saving) return;
    final classId = ref.read(currentClassIdProvider);
    final path = ref.read(currentWikiPagePathProvider);
    if (classId == null || path == null) return;

    setState(() => _saving = true);
    try {
      final apiClient = ref.read(apiClientProvider);
      await apiClient.updateWikiPage(classId, path, _editController.text);
      ref.invalidate(currentWikiPageProvider);
      if (mounted) setState(() => _editing = false);
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

  String _preprocessWikiLinks(String content) {
    return content.replaceAllMapped(RegExp(r'\[\[([^\]]+)\]\]'), (match) {
      final title = match.group(1)!;
      final slug = title.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]+'), '-');
      return '[$title](wiki://$slug)';
    });
  }

  void _handleLink(String? href) {
    if (href == null) return;

    if (href.startsWith('wiki://')) {
      final slug = href.substring('wiki://'.length);
      _navigateToWikiPage(slug);
    } else if (href.startsWith('hypatia://cite')) {
      final uri = Uri.parse(href);
      final file = uri.queryParameters['file'] ?? '';
      final loc = uri.queryParameters['loc'] ?? '';
      ref.read(sourceViewerRequestProvider.notifier).state =
          SourceViewerRequest(fileRef: file, location: loc);
    } else if (href.startsWith('http://') || href.startsWith('https://')) {
      launchUrl(Uri.parse(href), mode: LaunchMode.externalApplication);
    }
  }

  void _navigateToWikiPage(String slug) {
    final classId = ref.read(currentClassIdProvider);
    if (classId == null) return;

    final treeAsync = ref.read(wikiTreeProvider(classId));
    final pages = treeAsync.valueOrNull ?? [];

    final match = pages.where((p) {
      final pageSlug = p.title.toLowerCase().replaceAll(
        RegExp(r'[^a-z0-9]+'),
        '-',
      );
      return pageSlug == slug || p.path.endsWith(slug);
    }).firstOrNull;

    if (match != null) {
      ref.read(currentWikiPagePathProvider.notifier).state = match.path;
    }
  }

  String _formatDate(DateTime date) {
    return '${date.year}-${date.month.toString().padLeft(2, '0')}-'
        '${date.day.toString().padLeft(2, '0')}';
  }
}
