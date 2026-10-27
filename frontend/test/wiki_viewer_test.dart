import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/models/wiki_page.dart';
import 'package:frontend/providers/class_provider.dart';
import 'package:frontend/providers/file_provider.dart';
import 'package:frontend/providers/wiki_provider.dart';
import 'package:frontend/services/api_client.dart';
import 'package:frontend/widgets/wiki_viewer/wiki_viewer.dart';

const _classId = 'class-1';

WikiPage _page(String path, String content) => WikiPage(
  id: path,
  classId: _classId,
  path: path,
  title: path,
  category: WikiCategory.concept,
  content: content,
  createdAt: DateTime(2026),
  updatedAt: DateTime(2026),
);

class _FakeApi extends ApiClient {
  _FakeApi() : super(baseUrl: 'http://test');

  final pages = {
    'pages/x.md': _page('pages/x.md', '# X'),
    'pages/y.md': _page('pages/y.md', '# Y'),
  };
  final saves = <(String, String)>[];

  @override
  Future<WikiPage> getWikiPage(String classId, String pagePath) async =>
      pages[pagePath]!;

  @override
  Future<WikiPage> updateWikiPage(
    String classId,
    String pagePath,
    String content,
  ) async {
    saves.add((pagePath, content));
    return pages[pagePath] = _page(pagePath, content);
  }
}

void main() {
  testWidgets('an edit is saved to its own page after switching pages', (
    tester,
  ) async {
    final api = _FakeApi();
    final container = ProviderContainer(
      overrides: [
        apiClientProvider.overrideWithValue(api),
        currentClassIdProvider.overrideWith((ref) => _classId),
        wikiTreeProvider(_classId).overrideWith((ref) async => []),
        fileListProvider(_classId).overrideWith((ref) async => []),
      ],
    );
    addTearDown(container.dispose);
    final path = container.read(currentWikiPagePathProvider.notifier);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: Scaffold(body: WikiViewer())),
      ),
    );
    path.state = 'pages/x.md';
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Edit page'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '# X edited');

    // Open another page mid-edit: it shows normally, not X's editor.
    path.state = 'pages/y.md';
    await tester.pumpAndSettle();
    expect(find.byType(TextField), findsNothing);
    expect(find.byTooltip('Edit page'), findsOneWidget);

    // Back on X the edit resumes, and Save writes X.
    path.state = 'pages/x.md';
    await tester.pumpAndSettle();
    expect(find.text('# X edited'), findsOneWidget);
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(api.saves, [('pages/x.md', '# X edited')]);
    expect(container.read(wikiEditDraftsProvider), isEmpty);
    expect(find.byType(TextField), findsNothing);
  });
}
