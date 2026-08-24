import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/wiki_page.dart';
import '../services/api_client.dart';
import 'class_provider.dart';

final wikiTreeProvider = FutureProvider.family<List<WikiPageSummary>, String>((
  ref,
  classId,
) async {
  final apiClient = ref.read(apiClientProvider);
  return apiClient.getWikiTree(classId);
});

final currentWikiPagePathProvider = StateProvider<String?>((ref) => null);

final currentWikiPageProvider = FutureProvider<WikiPage?>((ref) async {
  final path = ref.watch(currentWikiPagePathProvider);
  if (path == null) return null;

  final classId = ref.watch(currentClassIdProvider);
  if (classId == null) return null;

  final apiClient = ref.read(apiClientProvider);
  return apiClient.getWikiPage(classId, path);
});
