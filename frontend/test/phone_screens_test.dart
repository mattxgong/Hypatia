import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:frontend/models/hypatia_class.dart';
import 'package:frontend/models/source_file.dart';
import 'package:frontend/models/wiki_page.dart';
import 'package:frontend/providers/class_provider.dart';
import 'package:frontend/providers/file_provider.dart';
import 'package:frontend/providers/theme_provider.dart';
import 'package:frontend/providers/wiki_provider.dart';
import 'package:frontend/screens/home_screen.dart';
import 'package:frontend/services/api_client.dart';
import 'package:frontend/widgets/chat_panel/command_input.dart';
import 'package:frontend/widgets/sidebar/wiki_tree.dart';
import 'package:frontend/widgets/wiki_viewer/wiki_viewer.dart';

const _classId = 'class-1';
const _phone = Size(390, 844);

class _OneClass extends ClassListNotifier {
  @override
  Future<List<HypatiaClass>> build() async => [
    HypatiaClass(
      id: _classId,
      name: 'Natural Language Processing',
      createdAt: DateTime(2026),
      updatedAt: DateTime(2026),
    ),
  ];
}

const _widePage = '''
# Smoothing methods compared

| Method | Idea | Strength | Weakness | Typical use |
|---|---|---|---|---|
| Laplace | Add one to every count, so unseen n-grams get some probability mass | Simple | Moves far too much mass to unseen events | Teaching |
| Good-Turing | Re-estimate counts from the frequency of frequencies | Principled | Unstable for large counts | Unigrams |
| Kneser-Ney | Continuation counts for lower orders | Best perplexity | More bookkeeping | Language models |
''';

WikiPage _page() => WikiPage(
  id: 'p1',
  classId: _classId,
  path: 'pages/concepts/smoothing.md',
  title: 'Smoothing methods for n-gram language models, compared',
  category: WikiCategory.concept,
  content: _widePage,
  createdAt: DateTime(2026),
  updatedAt: DateTime(2026),
);

WikiPageSummary _summary(String path, String title) => WikiPageSummary(
  id: path,
  path: path,
  title: title,
  category: WikiCategory.concept,
  updatedAt: DateTime(2026),
);

SourceFile _file() => SourceFile(
  id: 'f1',
  classId: _classId,
  originalFilename: 'lecture-04-language-models.pdf',
  fileType: FileType.pdf,
  fileSizeBytes: 1,
  rawPath: 'raw/lecture-04-language-models.pdf',
  convertedPath: 'converted/f1.md',
  status: FileStatus.ready,
  createdAt: DateTime(2026),
  updatedAt: DateTime(2026),
);

void main() {
  late SharedPreferences prefs;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
  });

  void setSize(WidgetTester tester, Size size) {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  List<Override> overrides() => [
    sharedPreferencesProvider.overrideWithValue(prefs),
    apiClientProvider.overrideWithValue(ApiClient(baseUrl: 'http://test')),
    classListProvider.overrideWith(_OneClass.new),
    currentClassIdProvider.overrideWith((ref) => _classId),
    wikiTreeProvider(_classId).overrideWith(
      (ref) async => [
        _summary('pages/concepts/smoothing.md', 'Smoothing'),
        _summary('pages/concepts/entropy.md', 'Entropy'),
      ],
    ),
    fileListProvider(_classId).overrideWith((ref) async => [_file()]),
    currentWikiPageProvider.overrideWith((ref) async => _page()),
  ];

  Future<void> pump(WidgetTester tester, Widget child) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: overrides(),
        child: MaterialApp(home: child),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('a wide table scrolls sideways instead of crushing columns', (
    tester,
  ) async {
    setSize(tester, _phone);
    await pump(tester, const Scaffold(body: WikiViewer()));

    expect(tester.takeException(), isNull);
    final table = find.byType(Table);
    expect(table, findsOneWidget);
    expect(
      find.ancestor(
        of: table,
        matching: find.byWidgetPredicate(
          (w) =>
              w is SingleChildScrollView &&
              w.scrollDirection == Axis.horizontal,
        ),
      ),
      findsOneWidget,
    );
    // Wider than the screen: the columns kept a readable width.
    expect(tester.getSize(table).width, greaterThan(_phone.width));
  });

  testWidgets('list rows are finger-sized on a touch screen', (tester) async {
    setSize(tester, _phone);
    await pump(
      tester,
      const Scaffold(body: WikiTree(content: WikiTreeContent.pages)),
    );

    final entropy = find.ancestor(
      of: find.text('Entropy'),
      matching: find.byType(ListTile),
    );
    expect(tester.getSize(entropy).height, greaterThanOrEqualTo(48));
  });

  testWidgets(
    'list rows stay compact on desktop',
    (tester) async {
      setSize(tester, const Size(1280, 800));
      await pump(
        tester,
        const Scaffold(body: WikiTree(content: WikiTreeContent.pages)),
      );

      final entropy = find.ancestor(
        of: find.text('Entropy'),
        matching: find.byType(ListTile),
      );
      expect(tester.getSize(entropy).height, lessThan(48));
    },
    variant: TargetPlatformVariant.only(TargetPlatform.windows),
  );

  testWidgets('a long-pressed source file opens a bottom sheet on a phone', (
    tester,
  ) async {
    setSize(tester, _phone);
    await pump(
      tester,
      const Scaffold(body: WikiTree(content: WikiTreeContent.sources)),
    );

    await tester.longPress(find.text('lecture-04-language-models.pdf'));
    await tester.pumpAndSettle();
    expect(find.byType(BottomSheet), findsOneWidget);
    expect(find.text('Delete…'), findsOneWidget);
    // The sheet is titled with the file it acts on.
    expect(find.text('lecture-04-language-models.pdf'), findsNWidgets(2));
  });

  testWidgets('a right-clicked source file opens a menu on desktop', (
    tester,
  ) async {
    setSize(tester, const Size(1280, 800));
    await pump(tester, const Scaffold(body: WikiTree()));

    await tester.longPress(find.text('lecture-04-language-models.pdf'));
    await tester.pumpAndSettle();
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.text('Delete…'), findsOneWidget);
  });

  testWidgets('the chat input stays above the keyboard', (tester) async {
    setSize(tester, _phone);
    tester.view.viewInsets = const FakeViewPadding(bottom: 320);
    addTearDown(tester.view.resetViewInsets);
    await pump(tester, const HomeScreen());

    await tester.tap(find.text('Chat'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    final input = tester.getRect(find.byType(CommandInput));
    expect(input.bottom, lessThanOrEqualTo(_phone.height - 320));
    // No desktop keyboard hints under the box on a phone.
    expect(find.textContaining('Shift+Enter'), findsNothing);
  });

  testWidgets('every phone tab fits with real content', (tester) async {
    setSize(tester, _phone);
    await pump(tester, const HomeScreen());

    for (final tab in ['Chat', 'Study', 'Sources', 'Wiki']) {
      await tester.tap(find.text(tab));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: tab);
    }
    // The open page, from the Wiki tab.
    await tester.tap(find.text('Smoothing'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.byType(WikiViewer), findsOneWidget);
  });
}
