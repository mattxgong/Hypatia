import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/wiki_page.dart';
import '../services/api_client.dart';
import 'class_provider.dart';

final searchBarFocusNodeProvider = Provider<FocusNode>((ref) {
  final node = FocusNode();
  ref.onDispose(node.dispose);
  return node;
});

final searchQueryProvider = StateProvider<String>((ref) {
  ref.watch(currentClassIdProvider);
  return '';
});

final searchCategoryProvider = StateProvider<String?>((ref) {
  ref.watch(currentClassIdProvider);
  return null;
});

final searchModeProvider = StateProvider<String>((ref) => 'hybrid');

final searchResultsProvider = FutureProvider<List<WikiSearchResult>>((
  ref,
) async {
  final query = ref.watch(searchQueryProvider);
  if (query.isEmpty) return [];

  final classId = ref.watch(currentClassIdProvider);
  if (classId == null) return [];

  final category = ref.watch(searchCategoryProvider);
  final mode = ref.watch(searchModeProvider);

  final apiClient = ref.read(apiClientProvider);
  return apiClient.searchWiki(classId, query, category: category, mode: mode);
});
