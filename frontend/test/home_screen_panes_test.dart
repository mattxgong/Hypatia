import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:frontend/models/hypatia_class.dart';
import 'package:frontend/providers/class_provider.dart';
import 'package:frontend/providers/layout_provider.dart';
import 'package:frontend/providers/study_provider.dart';
import 'package:frontend/providers/theme_provider.dart';
import 'package:frontend/providers/wiki_provider.dart';
import 'package:frontend/screens/home_screen.dart';
import 'package:frontend/widgets/chat_panel/chat_panel.dart';
import 'package:frontend/widgets/sidebar/sidebar.dart';

class _NoClasses extends ClassListNotifier {
  @override
  Future<List<HypatiaClass>> build() async => [];
}

Finder _divider(String label) => find.byWidgetPredicate(
  (w) => w is Semantics && w.properties.label == label,
);

void main() {
  late SharedPreferences prefs;
  late ProviderContainer container;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
  });

  Future<void> pumpHome(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    container = ProviderContainer(
      overrides: [
        sharedPreferencesProvider.overrideWithValue(prefs),
        classListProvider.overrideWith(_NoClasses.new),
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

  double sidebarWidth(WidgetTester tester) =>
      tester.getSize(find.byType(Sidebar)).width;

  testWidgets('dragging a divider resizes; double-click resets it', (
    tester,
  ) async {
    await pumpHome(tester);
    expect(sidebarWidth(tester), defaultSidebarWidth);

    await tester.drag(_divider('Resize class sidebar'), const Offset(60, 0));
    await tester.pumpAndSettle();
    // The gesture's touch slop takes the first few pixels of the drag.
    expect(sidebarWidth(tester), greaterThan(defaultSidebarWidth + 30));

    await tester.tap(_divider('Resize class sidebar'));
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tap(_divider('Resize class sidebar'));
    await tester.pumpAndSettle();
    expect(sidebarWidth(tester), defaultSidebarWidth);
  });

  testWidgets('saved widths are clamped when loaded', (tester) async {
    SharedPreferences.setMockInitialValues({sidebarWidthKey: 2000.0});
    prefs = await SharedPreferences.getInstance();
    await pumpHome(tester);

    expect(container.read(sidebarWidthProvider), maxSidebarWidth);
  });

  testWidgets('each pane hides from its own header and stays hidden', (
    tester,
  ) async {
    await pumpHome(tester);

    await tester.tap(find.byTooltip('Hide chat (Ctrl+J)'));
    await tester.pumpAndSettle();
    expect(find.byType(ChatPanel), findsNothing);
    expect(prefs.getBool(chatCollapsedKey), isTrue);

    await tester.tap(find.byTooltip('Hide sidebar (Ctrl+B)'));
    await tester.pumpAndSettle();
    expect(find.byType(Sidebar), findsNothing);
    expect(prefs.getBool(sidebarCollapsedKey), isTrue);

    // A fresh start reads the saved layout.
    await pumpHome(tester);
    expect(find.byType(ChatPanel), findsNothing);
    expect(find.byType(Sidebar), findsNothing);
  });

  testWidgets('the collapsed sidebar opens on the section picked', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({sidebarCollapsedKey: true});
    prefs = await SharedPreferences.getInstance();
    await pumpHome(tester);
    expect(find.byType(Sidebar), findsNothing);

    await tester.tap(find.byTooltip('Study'));
    await tester.pumpAndSettle();

    expect(find.byType(Sidebar), findsOneWidget);
    expect(container.read(sidebarModeProvider), SidebarMode.study);
  });

  testWidgets('an unsent chat draft survives a page switch and a collapse', (
    tester,
  ) async {
    await pumpHome(tester);
    final input = find.descendant(
      of: find.byType(ChatPanel),
      matching: find.byType(TextField),
    );
    await tester.enterText(input, 'half-written question');
    await tester.pump();

    container.read(currentWikiPagePathProvider.notifier).state =
        'pages/concept/x.md';
    await tester.pumpAndSettle();
    expect(find.text('half-written question'), findsOneWidget);

    await tester.tap(find.byTooltip('Hide chat (Ctrl+J)'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Show chat panel'));
    await tester.pumpAndSettle();
    expect(find.text('half-written question'), findsOneWidget);
  });
}
