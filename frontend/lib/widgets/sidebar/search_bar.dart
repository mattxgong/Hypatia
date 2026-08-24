import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/wiki_page.dart';
import '../../providers/class_provider.dart';
import '../../providers/wiki_provider.dart';
import '../../services/api_client.dart';

final searchQueryProvider = StateProvider<String>((ref) {
  ref.watch(currentClassIdProvider);
  return '';
});

final searchResultsProvider = FutureProvider<List<WikiSearchResult>>((
  ref,
) async {
  final query = ref.watch(searchQueryProvider);
  if (query.isEmpty) return [];

  final classId = ref.watch(currentClassIdProvider);
  if (classId == null) return [];

  final apiClient = ref.read(apiClientProvider);
  return apiClient.searchWiki(classId, query);
});

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

    return TextField(
      controller: _controller,
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

class SearchResults extends ConsumerWidget {
  const SearchResults({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final resultsAsync = ref.watch(searchResultsProvider);
    final theme = Theme.of(context);

    return resultsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Search error: $e')),
      data: (results) {
        if (results.isEmpty) {
          return Center(
            child: Text(
              'No results found',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
              ),
            ),
          );
        }

        return ListView.builder(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          itemCount: results.length,
          itemBuilder: (context, index) {
            final result = results[index];
            return ListTile(
              dense: true,
              visualDensity: VisualDensity.compact,
              title: Text(
                result.title,
                style: theme.textTheme.bodySmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
                overflow: TextOverflow.ellipsis,
              ),
              subtitle: Text(
                result.snippet,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
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
}
