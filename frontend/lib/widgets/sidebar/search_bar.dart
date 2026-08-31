import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/search_provider.dart';
import '../../providers/wiki_provider.dart';
import '../common/error_card.dart';

class SidebarSearchBar extends ConsumerStatefulWidget {
  const SidebarSearchBar({super.key});

  @override
  ConsumerState<SidebarSearchBar> createState() => _SidebarSearchBarState();
}

class _SidebarSearchBarState extends ConsumerState<SidebarSearchBar> {
  final _controller = TextEditingController();
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () {
      ref.read(searchQueryProvider.notifier).state = value.trim();
    });
  }

  void _clear() {
    _controller.clear();
    ref.read(searchQueryProvider.notifier).state = '';
  }

  @override
  Widget build(BuildContext context) {
    final query = ref.watch(searchQueryProvider);
    final focusNode = ref.watch(searchBarFocusNodeProvider);

    return TextField(
      controller: _controller,
      focusNode: focusNode,
      onChanged: _onChanged,
      decoration: InputDecoration(
        hintText: 'Search wiki...',
        prefixIcon: const Icon(Icons.search, size: 18),
        suffixIcon: query.isNotEmpty
            ? IconButton(
                icon: const Icon(Icons.clear, size: 16),
                onPressed: _clear,
              )
            : null,
        isDense: true,
      ),
    );
  }
}

class SearchModeSelector extends ConsumerWidget {
  const SearchModeSelector({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final mode = ref.watch(searchModeProvider);
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: SegmentedButton<String>(
        style: ButtonStyle(
          visualDensity: VisualDensity.compact,
          textStyle: WidgetStatePropertyAll(theme.textTheme.labelSmall),
          padding: const WidgetStatePropertyAll(
            EdgeInsets.symmetric(horizontal: 8),
          ),
        ),
        segments: const [
          ButtonSegment(value: 'hybrid', label: Text('Hybrid')),
          ButtonSegment(value: 'keyword', label: Text('Keyword')),
          ButtonSegment(value: 'semantic', label: Text('Semantic')),
        ],
        selected: {mode},
        onSelectionChanged: (selected) {
          ref.read(searchModeProvider.notifier).state = selected.first;
        },
      ),
    );
  }
}

class SearchCategoryFilter extends ConsumerWidget {
  const SearchCategoryFilter({super.key});

  static const _categories = [
    (null, 'All'),
    ('concept', 'Concepts'),
    ('entity', 'Entities'),
    ('source-summary', 'Sources'),
    ('synthesis', 'Synthesis'),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selected = ref.watch(searchCategoryProvider);

    return SizedBox(
      height: 32,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 8),
        itemCount: _categories.length,
        separatorBuilder: (_, i) => const SizedBox(width: 4),
        itemBuilder: (context, index) {
          final (value, label) = _categories[index];
          final isSelected = selected == value;
          return FilterChip(
            label: Text(label),
            selected: isSelected,
            onSelected: (_) {
              ref.read(searchCategoryProvider.notifier).state = value;
            },
            visualDensity: VisualDensity.compact,
            labelStyle: const TextStyle(fontSize: 11),
            padding: EdgeInsets.zero,
          );
        },
      ),
    );
  }
}

class SearchResults extends ConsumerWidget {
  const SearchResults({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final resultsAsync = ref.watch(searchResultsProvider);
    final theme = Theme.of(context);
    final query = ref.watch(searchQueryProvider);

    return resultsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Padding(
        padding: const EdgeInsets.all(12),
        child: ErrorCard(error: e, compact: true),
      ),
      data: (results) {
        if (results.isEmpty && query.isNotEmpty) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.search_off,
                    size: 36,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.3),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'No results found',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Try different keywords or switch search mode',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.4),
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ),
          );
        }

        if (results.isEmpty) {
          return const SizedBox.shrink();
        }

        return ListView.builder(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          itemCount: results.length,
          itemBuilder: (context, index) {
            final result = results[index];
            return ListTile(
              dense: true,
              visualDensity: VisualDensity.compact,
              title: Row(
                children: [
                  Expanded(
                    child: Text(
                      result.title,
                      style: theme.textTheme.bodySmall?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (result.category != null)
                    _CategoryBadge(category: result.category!),
                ],
              ),
              subtitle: result.snippet.isNotEmpty
                  ? RichText(
                      text: _buildHighlightedSnippet(result.snippet, theme),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    )
                  : null,
              onTap: () {
                ref.read(currentWikiPagePathProvider.notifier).state =
                    result.path;
                ref.read(searchQueryProvider.notifier).state = '';
              },
            );
          },
        );
      },
    );
  }

  TextSpan _buildHighlightedSnippet(String snippet, ThemeData theme) {
    final baseStyle =
        theme.textTheme.bodySmall?.copyWith(
          color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
        ) ??
        const TextStyle();
    final boldStyle = baseStyle.copyWith(fontWeight: FontWeight.bold);

    final spans = <TextSpan>[];
    final regex = RegExp(r'<b>(.*?)</b>');
    var lastEnd = 0;

    for (final match in regex.allMatches(snippet)) {
      if (match.start > lastEnd) {
        spans.add(
          TextSpan(
            text: _stripTags(snippet.substring(lastEnd, match.start)),
            style: baseStyle,
          ),
        );
      }
      spans.add(TextSpan(text: match.group(1), style: boldStyle));
      lastEnd = match.end;
    }

    if (lastEnd < snippet.length) {
      spans.add(
        TextSpan(
          text: _stripTags(snippet.substring(lastEnd)),
          style: baseStyle,
        ),
      );
    }

    return TextSpan(children: spans);
  }

  String _stripTags(String html) {
    return html.replaceAll(RegExp(r'<[^>]*>'), '');
  }
}

class _CategoryBadge extends StatelessWidget {
  const _CategoryBadge({required this.category});

  final String category;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final (label, color) = _categoryInfo(category);

    return Container(
      margin: const EdgeInsets.only(left: 4),
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        label,
        style: theme.textTheme.labelSmall?.copyWith(color: color, fontSize: 9),
      ),
    );
  }

  (String, Color) _categoryInfo(String category) {
    return switch (category) {
      'concept' => ('CONCEPT', Colors.blue),
      'entity' => ('ENTITY', Colors.purple),
      'source-summary' => ('SOURCE', Colors.orange),
      'synthesis' => ('SYNTH', Colors.teal),
      'index' => ('INDEX', Colors.grey),
      _ => (category.toUpperCase(), Colors.grey),
    };
  }
}
