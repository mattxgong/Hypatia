import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:frontend/providers/class_provider.dart';
import 'package:frontend/providers/theme_provider.dart';
import 'package:frontend/widgets/sidebar/sidebar.dart';

void main() {
  late SharedPreferences prefs;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
  });

  Widget wrapWithProviders(Widget child, {String? classId}) {
    return ProviderScope(
      overrides: [
        sharedPreferencesProvider.overrideWithValue(prefs),
        if (classId != null)
          currentClassIdProvider.overrideWith((ref) => classId),
      ],
      child: MaterialApp(
        home: Scaffold(body: SizedBox(width: 250, child: child)),
      ),
    );
  }

  void setLargeTestSurface(WidgetTester tester) {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  testWidgets('Sidebar renders class dropdown and search bar', (tester) async {
    setLargeTestSurface(tester);
    await tester.pumpWidget(
      wrapWithProviders(const Sidebar(), classId: 'class-1'),
    );
    await tester.pumpAndSettle();

    expect(find.text('Machine Learning'), findsOneWidget);
    expect(find.byType(TextField), findsWidgets);
    expect(find.text('Search wiki...'), findsOneWidget);
  });

  testWidgets('Sidebar shows wiki tree categories', (tester) async {
    setLargeTestSurface(tester);
    await tester.pumpWidget(
      wrapWithProviders(const Sidebar(), classId: 'class-1'),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Concepts'), findsOneWidget);
    expect(find.textContaining('Source Summaries'), findsOneWidget);
    expect(find.textContaining('Entities'), findsOneWidget);
    expect(find.textContaining('Source Files'), findsOneWidget);
  });

  testWidgets('Wiki tree shows pages under categories', (tester) async {
    setLargeTestSurface(tester);
    await tester.pumpWidget(
      wrapWithProviders(const Sidebar(), classId: 'class-1'),
    );
    await tester.pumpAndSettle();

    expect(find.text('Neural Networks'), findsOneWidget);
    expect(find.text('Backpropagation'), findsOneWidget);
    expect(find.text('Geoffrey Hinton'), findsOneWidget);
  });

  testWidgets('Sidebar shows Add Files button', (tester) async {
    setLargeTestSurface(tester);
    await tester.pumpWidget(
      wrapWithProviders(const Sidebar(), classId: 'class-1'),
    );
    await tester.pumpAndSettle();

    expect(find.text('Add Files'), findsOneWidget);
  });

  testWidgets('Sidebar shows theme toggle', (tester) async {
    setLargeTestSurface(tester);
    await tester.pumpWidget(
      wrapWithProviders(const Sidebar(), classId: 'class-1'),
    );
    await tester.pumpAndSettle();

    expect(find.byTooltip('Toggle theme'), findsOneWidget);
  });
}
