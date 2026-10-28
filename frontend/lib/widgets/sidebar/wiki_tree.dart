import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/source_file.dart';
import '../../models/wiki_page.dart';
import '../../providers/class_provider.dart';
import '../../providers/file_provider.dart';
import '../../providers/wiki_provider.dart';
import '../common/error_card.dart';
import '../source_viewer/source_viewer.dart';
import 'source_file_actions.dart';

class WikiTree extends ConsumerWidget {
  const WikiTree({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final classId = ref.watch(currentClassIdProvider);
    if (classId == null) {
      return const Center(child: Text('Select a class'));
    }

    final pagesAsync = ref.watch(wikiTreeProvider(classId));
    final filesAsync = ref.watch(fileListProvider(classId));
    final currentPath = ref.watch(currentWikiPagePathProvider);

    return pagesAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Padding(
        padding: const EdgeInsets.all(12),
        child: ErrorCard(
          error: e,
          compact: true,
          onRetry: () => ref.invalidate(wikiTreeProvider(classId)),
        ),
      ),
      data: (pages) {
        final files = filesAsync.valueOrNull ?? [];

        final concepts = pages
            .where((p) => p.category == WikiCategory.concept)
            .toList();
        final summaries = pages
            .where((p) => p.category == WikiCategory.sourceSummary)
            .toList();
        final entities = pages
            .where((p) => p.category == WikiCategory.entity)
            .toList();
        final indexPage = pages.where(
          (p) => p.category == WikiCategory.wikiIndex,
        );

        void open(String path) =>
            ref.read(currentWikiPagePathProvider.notifier).state = path;
        final collapsed = ref.watch(_collapsedSectionsProvider);
        // One flat, lazily built list: a ListView of ExpansionTiles built
        // every row of every section up front, which doesn't scale to a large
        // wiki.
        final rows = <Widget Function()>[
          if (indexPage.isNotEmpty)
            () => _PageTile(
              page: indexPage.first,
              isSelected: currentPath == indexPage.first.path,
              onTap: () => open(indexPage.first.path),
            ),
          for (final (title, icon, items) in [
            ('Concepts', Icons.lightbulb_outline, concepts),
            ('Source Summaries', Icons.description_outlined, summaries),
            ('Entities', Icons.person_outline, entities),
          ]) ...[
            () => _CategoryHeader(
              title: title,
              icon: icon,
              count: items.length,
              expanded: !collapsed.contains(title),
              onToggle: () => _toggleSection(ref, title),
            ),
            if (!collapsed.contains(title))
              for (final p in items)
                () => Padding(
                  padding: const EdgeInsets.only(left: 16),
                  child: _PageTile(
                    page: p,
                    isSelected: currentPath == p.path,
                    onTap: () => open(p.path),
                  ),
                ),
          ],
          () => _CategoryHeader(
            title: 'Source Files',
            icon: Icons.folder_outlined,
            count: files.length,
            expanded: !collapsed.contains('Source Files'),
            onToggle: () => _toggleSection(ref, 'Source Files'),
          ),
          if (!collapsed.contains('Source Files'))
            for (final f in files)
              () => Padding(
                padding: const EdgeInsets.only(left: 16),
                child: _FileTile(
                  file: f,
                  onTap: f.convertedPath == null
                      ? null
                      : () => showConvertedSourceViewer(context, classId, f),
                  onMenu: (position) =>
                      showSourceFileMenu(context, ref, classId, f, position),
                ),
              ),
        ];

        return ListView.builder(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          itemCount: rows.length,
          itemBuilder: (context, index) => rows[index](),
        );
      },
    );
  }

  void _toggleSection(WidgetRef ref, String title) {
    final notifier = ref.read(_collapsedSectionsProvider.notifier);
    notifier.state = notifier.state.contains(title)
        ? ({...notifier.state}..remove(title))
        : {...notifier.state, title};
  }
}

/// Sidebar sections the user has collapsed.
final _collapsedSectionsProvider = StateProvider<Set<String>>((ref) => {});

class _CategoryHeader extends StatelessWidget {
  const _CategoryHeader({
    required this.title,
    required this.icon,
    required this.count,
    required this.expanded,
    required this.onToggle,
  });

  final String title;
  final IconData icon;
  final int count;
  final bool expanded;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListTile(
      dense: true,
      visualDensity: VisualDensity.compact,
      contentPadding: const EdgeInsets.symmetric(horizontal: 8),
      leading: Icon(icon, size: 18),
      title: Text(
        '$title ($count)',
        style: theme.textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w600),
      ),
      trailing: Icon(
        expanded ? Icons.expand_less : Icons.expand_more,
        size: 18,
      ),
      onTap: onToggle,
    );
  }
}

class _PageTile extends StatelessWidget {
  const _PageTile({
    required this.page,
    required this.isSelected,
    required this.onTap,
  });

  final WikiPageSummary page;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListTile(
      dense: true,
      visualDensity: VisualDensity.compact,
      selected: isSelected,
      selectedTileColor: theme.colorScheme.primaryContainer.withValues(
        alpha: 0.3,
      ),
      title: Text(
        page.title,
        style: theme.textTheme.bodySmall,
        overflow: TextOverflow.ellipsis,
      ),
      leading: const Icon(Icons.article_outlined, size: 16),
      onTap: onTap,
    );
  }
}

class _FileTile extends StatelessWidget {
  const _FileTile({
    required this.file,
    required this.onTap,
    required this.onMenu,
  });

  final SourceFile file;
  final VoidCallback? onTap;

  /// Opens the file's actions (Open, Retry, Delete) at a global position.
  final void Function(Offset position) onMenu;

  IconData get _statusIcon {
    switch (file.status) {
      case FileStatus.ready:
        return Icons.check_circle_outline;
      case FileStatus.processing:
        return Icons.hourglass_top;
      case FileStatus.error:
        return Icons.error_outline;
      case FileStatus.pending:
        return Icons.schedule;
    }
  }

  String? get _busyMessage {
    if (file.isConverting) return 'Converting to markdown...';
    if (file.isSummarizing) return 'Generating source summary...';
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final busyMessage = _busyMessage;
    final hasError = file.status == FileStatus.error;
    final icon = Icon(
      file.convertedPath != null && !hasError
          ? Icons.description_outlined
          : _statusIcon,
      size: 16,
    );
    final tile = ListTile(
      dense: true,
      visualDensity: VisualDensity.compact,
      title: Text(
        file.originalFilename,
        style: theme.textTheme.bodySmall,
        overflow: TextOverflow.ellipsis,
      ),
      leading: hasError
          ? Tooltip(
              message: file.errorMessage ?? 'Processing failed',
              child: icon,
            )
          : icon,
      trailing: busyMessage == null
          ? (hasError
                ? Icon(Icons.refresh, size: 16, color: theme.colorScheme.error)
                : null)
          : Tooltip(
              message: busyMessage,
              child: const SizedBox(
                width: 12,
                height: 12,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
      onTap: onTap ?? (hasError ? () => onMenu(_center(context)) : null),
    );
    return GestureDetector(
      onSecondaryTapUp: (details) => onMenu(details.globalPosition),
      onLongPressStart: (details) => onMenu(details.globalPosition),
      child: Semantics(
        hint: 'Right-click or long-press for file actions',
        child: tile,
      ),
    );
  }

  Offset _center(BuildContext context) {
    final box = context.findRenderObject() as RenderBox?;
    return box == null
        ? Offset.zero
        : box.localToGlobal(box.size.center(Offset.zero));
  }
}
