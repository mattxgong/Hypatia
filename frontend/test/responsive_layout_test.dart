import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:frontend/models/hypatia_class.dart';
import 'package:frontend/providers/class_provider.dart';
import 'package:frontend/providers/layout_provider.dart';
import 'package:frontend/providers/search_provider.dart';
import 'package:frontend/providers/study_provider.dart';
import 'package:frontend/providers/theme_provider.dart';
import 'package:frontend/providers/wiki_provider.dart';
import 'package:frontend/screens/home_screen.dart';
import 'package:frontend/utils/window_size.dart';
import 'package:frontend/widgets/chat_panel/chat_panel.dart';
import 'package:frontend/widgets/sidebar/add_file_button.dart';
import 'package:frontend/widgets/sidebar/class_dropdown.dart';
import 'package:frontend/widgets/sidebar/search_bar.dart';
import 'package:frontend/widgets/sidebar/sidebar.dart';
import 'package:frontend/widgets/study/flashcard_review.dart';
import 'package:frontend/widgets/study/study_panel.dart';

class _NoClasses extends ClassListNotifier {
  @override
  Future<List<HypatiaClass>> build() async => [];
}

// The test matrix from the plan (10.12), in logical pixels.
const _phone = Size(390, 844);
const _foldable = Size(673, 841);
const _tabletPortrait = Size(800, 1280);
const _tabletLandscape = Size(1280, 800);

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
        classListProvider.overrideWith(_NoClasses.new),
        // No page loads in these tests; the viewer shows its placeholder.
        currentWikiPageProvider.overrideWith((ref) async => null),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: HomeScreen()),
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> back(WidgetTester tester) async {
    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
  }

  test('size classes follow the Material 3 breakpoints', () {
    expect(windowSizeClassFor(390), WindowSizeClass.compact);
    expect(windowSizeClassFor(599.9), WindowSizeClass.compact);
    expect(windowSizeClassFor(600), WindowSizeClass.medium);
    expect(windowSizeClassFor(_foldable.width), WindowSizeClass.medium);
    expect(windowSizeClassFor(_tabletPortrait.width), WindowSizeClass.medium);
    expect(windowSizeClassFor(840), WindowSizeClass.expanded);
    expect(
      windowSizeClassFor(_tabletLandscape.width),
      WindowSizeClass.expanded,
    );
  });

  group('phone', () {
    testWidgets('one pane at a time, picked from the bottom bar', (
      tester,
    ) async {
      await pumpHome(tester, _phone);

      expect(find.byType(NavigationBar), findsOneWidget);
      expect(find.byType(Sidebar), findsNothing);
      expect(find.byType(NavigationRail), findsNothing);
      // The Class is in the app bar, its other actions in the menu.
      expect(find.byType(ClassDropdown), findsOneWidget);
      expect(find.byTooltip('Class settings'), findsNothing);
      expect(find.byTooltip('More'), findsOneWidget);

      await tester.tap(find.text('Chat'));
      await tester.pumpAndSettle();
      expect(find.byType(ChatPanel), findsOneWidget);
      // Chat is a tab here, not a pane that hides.
      expect(find.byTooltip('Hide chat (Ctrl+J)'), findsNothing);

      await tester.tap(find.text('Sources'));
      await tester.pumpAndSettle();
      expect(find.byType(AddFileButton), findsOneWidget);

      await tester.tap(find.text('Study'));
      await tester.pumpAndSettle();
      expect(find.byType(StudyPanel), findsOneWidget);
      expect(container.read(sidebarModeProvider), SidebarMode.study);
    });

    testWidgets('Back closes the open page, then returns to the Wiki tab', (
      tester,
    ) async {
      await pumpHome(tester, _phone);

      container.read(currentWikiPagePathProvider.notifier).state =
          'pages/concepts/entropy.md';
      await tester.pumpAndSettle();
      expect(find.widgetWithText(TextButton, 'Wiki'), findsOneWidget);

      await back(tester);
      expect(container.read(currentWikiPagePathProvider), isNull);

      await tester.tap(find.text('Chat'));
      await tester.pumpAndSettle();
      await back(tester);
      expect(container.read(compactDestinationProvider), HomeDestination.wiki);
    });

    testWidgets('a deck opened from chat shows on the Study tab, and stays '
        'open while the wiki is browsed', (tester) async {
      await pumpHome(tester, _phone);
      await tester.tap(find.text('Chat'));
      await tester.pumpAndSettle();

      container.read(studySelectionProvider.notifier).state =
          const StudySelection(StudyKind.deck, 'd1');
      await tester.pump();
      expect(container.read(compactDestinationProvider), HomeDestination.study);

      container.read(currentWikiPagePathProvider.notifier).state =
          'pages/index.md';
      await tester.pump();
      expect(container.read(compactDestinationProvider), HomeDestination.wiki);
      expect(container.read(studySelectionProvider), isNotNull);
    });

    testWidgets('search opens in the app bar and Back closes it', (
      tester,
    ) async {
      await pumpHome(tester, _phone);

      await tester.tap(find.byTooltip('Search wiki (Ctrl+K)'));
      await tester.pumpAndSettle();
      expect(find.byType(SidebarSearchBar), findsOneWidget);
      expect(find.text("Search this class's wiki."), findsOneWidget);

      await back(tester);
      expect(container.read(searchOpenProvider), isFalse);
      expect(find.byType(SidebarSearchBar), findsNothing);
    });
  });

  group('tablet portrait and foldable', () {
    for (final (name, size) in [
      ('tablet portrait', _tabletPortrait),
      ('foldable', _foldable),
    ]) {
      testWidgets('$name: two panes and a rail', (tester) async {
        await pumpHome(tester, size);

        expect(find.byType(NavigationRail), findsOneWidget);
        expect(find.byType(NavigationBar), findsNothing);
        expect(find.byType(Sidebar), findsNothing);
        expect(find.byType(ChatPanel), findsOneWidget);
        expect(_semantics('Resize panes'), findsOneWidget);
      });
    }

    testWidgets('the rail switches the second pane; decks open beside it', (
      tester,
    ) async {
      await pumpHome(tester, _tabletPortrait);

      await tester.tap(find.text('Study'));
      await tester.pumpAndSettle();
      expect(find.byType(StudyPanel), findsOneWidget);
      expect(find.byType(ChatPanel), findsNothing);

      container.read(studySelectionProvider.notifier).state =
          const StudySelection(StudyKind.deck, 'd1');
      await tester.pump();
      // The list stays beside the open deck; Back closes the deck.
      expect(find.byType(StudyPanel), findsOneWidget);
      await back(tester);
      expect(container.read(studySelectionProvider), isNull);
    });

    testWidgets('the split drags, with a touch-sized handle, and is saved', (
      tester,
    ) async {
      await pumpHome(tester, _tabletPortrait);
      final handle = _semantics('Resize panes');
      expect(tester.getSize(handle).width, greaterThanOrEqualTo(24));
      final before = tester.getSize(find.byType(ChatPanel)).width;

      await tester.drag(handle, const Offset(-80, 0));
      await tester.pump(const Duration(milliseconds: 500));
      expect(tester.getSize(find.byType(ChatPanel)).width, greaterThan(before));
      expect(
        prefs.getDouble(secondaryPaneFractionKey),
        container.read(secondaryPaneFractionProvider),
      );
    });
  });

  testWidgets('tablet landscape: the three-pane layout', (tester) async {
    await pumpHome(tester, _tabletLandscape);

    expect(find.byType(Sidebar), findsOneWidget);
    expect(find.byType(ChatPanel), findsOneWidget);
    expect(find.byType(NavigationRail), findsNothing);
    expect(find.byType(NavigationBar), findsNothing);
  });

  testWidgets('the smallest desktop window still fits the phone layout', (
    tester,
  ) async {
    await pumpHome(tester, const Size(360, 560));
    for (final tab in ['Chat', 'Study', 'Sources', 'Wiki']) {
      await tester.tap(find.text(tab));
      await tester.pumpAndSettle();
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('rotating mid-review keeps the same review session', (
    tester,
  ) async {
    await pumpHome(tester, _tabletPortrait);
    container.read(studySelectionProvider.notifier).state =
        const StudySelection(StudyKind.deck, 'd1');
    await tester.pumpAndSettle();
    final review = tester.state(find.byType(FlashcardReview));

    setSize(tester, _tabletLandscape);
    await tester.pumpAndSettle();
    expect(tester.state(find.byType(FlashcardReview)), same(review));

    setSize(tester, _phone);
    await tester.pumpAndSettle();
    expect(tester.state(find.byType(FlashcardReview)), same(review));
  });

  testWidgets('changing size class keeps the search and the chat', (
    tester,
  ) async {
    await pumpHome(tester, _phone);
    await tester.tap(find.text('Chat'));
    await tester.pumpAndSettle();
    final chat = tester.element(find.byType(ChatPanel));
    container.read(searchQueryProvider.notifier).state = 'entropy';
    await tester.pumpAndSettle();

    // Rotate to a tablet's landscape width: a different layout.
    setSize(tester, _tabletLandscape);
    await tester.pumpAndSettle();
    expect(find.byType(Sidebar), findsOneWidget);
    // The same chat, moved rather than rebuilt from scratch.
    expect(tester.element(find.byType(ChatPanel)), same(chat));
    // The sidebar's search box shows the query typed on the phone layout.
    expect(find.widgetWithText(TextField, 'entropy'), findsOneWidget);

    setSize(tester, _tabletPortrait);
    await tester.pumpAndSettle();
    expect(find.byType(NavigationRail), findsOneWidget);
    expect(tester.element(find.byType(ChatPanel)), same(chat));
  });

  testWidgets('Class settings opens on top, so Back returns to the Class', (
    tester,
  ) async {
    final router = GoRouter(
      routes: [
        GoRoute(
          path: '/',
          builder: (context, _) => Scaffold(
            body: TextButton(
              onPressed: () => openClassSettings(context, 'c1'),
              child: const Text('open'),
            ),
          ),
        ),
        GoRoute(
          path: '/class/:classId/settings',
          builder: (_, _) => const Scaffold(body: Text('settings')),
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(MaterialApp.router(routerConfig: router));

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('settings'), findsOneWidget);

    await back(tester);
    expect(find.text('open'), findsOneWidget);
  });
}
