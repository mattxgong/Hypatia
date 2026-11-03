import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:frontend/models/hypatia_class.dart';
import 'package:frontend/models/wiki_page.dart';
import 'package:frontend/providers/class_provider.dart';
import 'package:frontend/providers/file_provider.dart';
import 'package:frontend/providers/layout_provider.dart';
import 'package:frontend/providers/theme_provider.dart';
import 'package:frontend/providers/wiki_provider.dart';
import 'package:frontend/screens/home_screen.dart';
import 'package:frontend/services/api_client.dart';
import 'package:frontend/widgets/source_viewer/source_viewer.dart';
import 'package:frontend/widgets/wiki_viewer/wiki_viewer.dart';

const _classId = 'class-1';
const _landscape = Size(1280, 800);
const _portrait = Size(800, 1280);

const _citation = SourceViewerRequest(fileRef: 'f1', location: 'p:3');

class _OneClass extends ClassListNotifier {
  @override
  Future<List<HypatiaClass>> build() async => [
    HypatiaClass(
      id: _classId,
      name: 'NLP',
      createdAt: DateTime(2026),
      updatedAt: DateTime(2026),
    ),
  ];
}

WikiPage _longPage() => WikiPage(
  id: 'p1',
  classId: _classId,
  path: 'pages/concepts/hmm.md',
  title: 'Hidden Markov models',
  category: WikiCategory.concept,
  content: [
    for (var i = 1; i <= 80; i++) 'Paragraph $i about hidden states.\n',
  ].join('\n'),
  createdAt: DateTime(2026),
  updatedAt: DateTime(2026),
);

Finder _semantics(String label) => find.byWidgetPredicate(
  (w) => w is Semantics && w.properties.label == label,
);

void main() {
  late SharedPreferences prefs;
  late ProviderContainer container;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
  });

  void setSize(WidgetTester tester, Size size) {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1.0;
  }

  Future<void> pumpHome(WidgetTester tester, Size size) async {
    setSize(tester, size);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    container = ProviderContainer(
      overrides: [
        sharedPreferencesProvider.overrideWithValue(prefs),
        apiClientProvider.overrideWithValue(ApiClient(baseUrl: 'http://test')),
        classListProvider.overrideWith(_OneClass.new),
        currentClassIdProvider.overrideWith((ref) => _classId),
        wikiTreeProvider(_classId).overrideWith((ref) async => []),
        fileListProvider(_classId).overrideWith((ref) async => []),
        currentWikiPageProvider.overrideWith((ref) async => _longPage()),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: HomeScreen()),
      ),
    );
    container.read(currentWikiPagePathProvider.notifier).state =
        'pages/concepts/hmm.md';
    await tester.pumpAndSettle();
  }

  Future<void> cite(WidgetTester tester) async {
    container.read(sourceViewerRequestProvider.notifier).state = _citation;
    await tester.pumpAndSettle();
  }

  group('tablet in landscape', () {
    testWidgets('dividers and collapsed strips are finger-sized', (
      tester,
    ) async {
      await pumpHome(tester, _landscape);
      expect(
        tester.getSize(_semantics('Resize class sidebar')).width,
        greaterThanOrEqualTo(24),
      );

      container.read(chatPanelCollapsedProvider.notifier).state = true;
      await tester.pumpAndSettle();
      expect(
        tester.getSize(_semantics('Show chat panel')).width,
        greaterThanOrEqualTo(48),
      );
    });

    testWidgets('a citation opens beside the page, and Back closes it', (
      tester,
    ) async {
      await pumpHome(tester, _landscape);
      await cite(tester);

      expect(find.byType(SourcePanel), findsOneWidget);
      expect(find.byType(Dialog), findsNothing);
      // The page stays in view beside it.
      expect(find.text('Hidden Markov models'), findsOneWidget);
      expect(
        tester.getRect(find.byType(SourcePanel)).left,
        greaterThan(tester.getRect(find.byType(WikiViewer)).right - 1),
      );

      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(find.byType(SourcePanel), findsNothing);
      expect(container.read(currentWikiPagePathProvider), isNotNull);
    });

    testWidgets('turning to portrait moves an open source into a dialog', (
      tester,
    ) async {
      await pumpHome(tester, _landscape);
      await cite(tester);

      setSize(tester, _portrait);
      await tester.pumpAndSettle();
      expect(find.byType(SourceViewerDialog), findsOneWidget);
      expect(container.read(sideSourceProvider), isNull);
    });

    testWidgets('turning keeps the reading position', (tester) async {
      await pumpHome(tester, _landscape);
      final scrollable = find
          .descendant(
            of: find.byType(WikiViewer),
            matching: find.byType(Scrollable),
          )
          .first;
      await tester.drag(scrollable, const Offset(0, -900));
      await tester.pumpAndSettle();
      final before = tester.state<ScrollableState>(scrollable).position.pixels;
      expect(before, greaterThan(0));

      setSize(tester, _portrait);
      await tester.pumpAndSettle();
      expect(tester.state<ScrollableState>(scrollable).position.pixels, before);
    });
  });

  group('desktop', () {
    final windows = TargetPlatformVariant.only(TargetPlatform.windows);

    testWidgets('dividers stay mouse-sized', (tester) async {
      await pumpHome(tester, _landscape);
      expect(tester.getSize(_semantics('Resize class sidebar')).width, 12);
    }, variant: windows);

    testWidgets('a citation opens in a dialog, as before', (tester) async {
      await pumpHome(tester, _landscape);
      await cite(tester);
      expect(find.byType(SourceViewerDialog), findsOneWidget);
      expect(container.read(sideSourceProvider), isNull);
    }, variant: windows);
  });

  testWidgets('an iPad keyboard uses Cmd for shortcuts', (tester) async {
    await pumpHome(tester, _portrait);

    await tester.sendKeyDownEvent(LogicalKeyboardKey.metaLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.keyK);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.metaLeft);
    await tester.pumpAndSettle();
    expect(container.read(searchOpenProvider), isTrue);
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));
}
