import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/source_file.dart';
import '../../models/wiki_page.dart';
import '../../providers/class_provider.dart';
import '../../providers/file_provider.dart';
import '../../providers/wiki_provider.dart';
import '../common/error_card.dart';
import '../source_viewer/source_viewer.dart';

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

        return ListView(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          children: [
            if (indexPage.isNotEmpty)
              _PageTile(
                page: indexPage.first,
                isSelected: currentPath == indexPage.first.path,
                onTap: () =>
                    ref.read(currentWikiPagePathProvider.notifier).state =
                        indexPage.first.path,
              ),
            _CategorySection(
              title: 'Concepts',
              icon: Icons.lightbulb_outline,
              children: concepts
                  .map(
                    (p) => _PageTile(
                      page: p,
                      isSelected: currentPath == p.path,
                      onTap: () =>
                          ref.read(currentWikiPagePathProvider.notifier).state =
                              p.path,
                    ),
                  )
                  .toList(),
            ),
            _CategorySection(
              title: 'Source Summaries',
              icon: Icons.description_outlined,
              children: summaries
                  .map(
                    (p) => _PageTile(
                      page: p,
                      isSelected: currentPath == p.path,
                      onTap: () =>
                          ref.read(currentWikiPagePathProvider.notifier).state =
                              p.path,
                    ),
                  )
                  .toList(),
            ),
            _CategorySection(
              title: 'Entities',
              icon: Icons.person_outline,
              children: entities
                  .map(
                    (p) => _PageTile(
                      page: p,
                      isSelected: currentPath == p.path,
                      onTap: () =>
                          ref.read(currentWikiPagePathProvider.notifier).state =
                              p.path,
                    ),
                  )
                  .toList(),
            ),
            _CategorySection(
              title: 'Source Files',
              icon: Icons.folder_outlined,
              children: files
                  .map(
                    (f) => _FileTile(
                      file: f,
                      onTap: f.convertedPath == null
                          ? null
                          : () =>
                                showConvertedSourceViewer(context, classId, f),
                    ),
                  )
                  .toList(),
            ),
          ],
        );
      },
    );
  }
}

class _CategorySection extends StatelessWidget {
  const _CategorySection({
    required this.title,
    required this.icon,
    required this.children,
  });

  final String title;
  final IconData icon;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ExpansionTile(
      leading: Icon(icon, size: 18),
      title: Text(
        '$title (${children.length})',
        style: theme.textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w600),
      ),
      dense: true,
      tilePadding: const EdgeInsets.symmetric(horizontal: 8),
      childrenPadding: const EdgeInsets.only(left: 16),
      initiallyExpanded: true,
      children: children,
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
  const _FileTile({required this.file, required this.onTap});

  final SourceFile file;
  final VoidCallback? onTap;

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
    return ListTile(
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
          ? null
          : Tooltip(
              message: busyMessage,
              child: const SizedBox(
                width: 12,
                height: 12,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
      onTap: onTap,
    );
  }
}
